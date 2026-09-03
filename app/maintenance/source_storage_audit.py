"""Classify source-storage objects against current knowledge-unit state."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from app.infrastructure.source_storage import SourceObject


@dataclass(frozen=True, slots=True)
class ExpectedSource:
    unit_code: str
    content_hash: str | None
    file_type: str | None
    source_file_name: str | None


@dataclass(frozen=True, slots=True)
class SourceAuditEntry:
    status: str
    object: SourceObject
    expected_hash: str | None = None
    detail: str = ""

    def to_dict(self) -> dict:
        payload = asdict(self)
        modified_at = self.object.modified_at
        payload["object"]["modified_at"] = modified_at.isoformat() if modified_at else None
        return payload


@dataclass(frozen=True, slots=True)
class SourceAuditReport:
    entries: tuple[SourceAuditEntry, ...]
    missing_current_sources: tuple[str, ...]

    def counts(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for entry in self.entries:
            result[entry.status] = result.get(entry.status, 0) + 1
        if self.missing_current_sources:
            result["missing_current_source"] = len(self.missing_current_sources)
        return result

    def to_dict(self) -> dict:
        return {
            "counts": self.counts(),
            "missing_current_sources": list(self.missing_current_sources),
            "entries": [entry.to_dict() for entry in self.entries],
        }


def classify_source_objects(
    objects: list[SourceObject],
    expected: dict[str, ExpectedSource],
) -> SourceAuditReport:
    entries: list[SourceAuditEntry] = []
    available_current: set[str] = set()
    available_legacy: set[str] = set()

    for item in objects:
        if item.malformed or not item.unit_code:
            entries.append(
                SourceAuditEntry(
                    status="malformed",
                    object=item,
                    detail="unrecognized source-object key; never auto-delete",
                )
            )
            continue

        target = expected.get(item.unit_code)
        if target is None:
            entries.append(
                SourceAuditEntry(
                    status="orphan_legacy" if item.legacy else "orphan_unit",
                    object=item,
                    detail="source object has no matching knowledge unit",
                )
            )
            continue

        if item.legacy:
            available_legacy.add(item.unit_code)
            entries.append(
                SourceAuditEntry(
                    status="legacy_attached",
                    object=item,
                    expected_hash=target.content_hash,
                    detail="legacy unit_code source remains readable but is not hash-versioned",
                )
            )
            continue

        if target.content_hash and item.content_hash == target.content_hash:
            available_current.add(item.unit_code)
            entries.append(
                SourceAuditEntry(
                    status="current",
                    object=item,
                    expected_hash=target.content_hash,
                )
            )
        else:
            entries.append(
                SourceAuditEntry(
                    status="stale_version",
                    object=item,
                    expected_hash=target.content_hash,
                    detail="unit exists but object hash is not the current DB content_hash",
                )
            )

    missing = sorted(
        source.unit_code
        for source in expected.values()
        if source.source_file_name
        and source.unit_code not in available_current
        and source.unit_code not in available_legacy
    )
    entries.sort(key=lambda entry: (entry.status, entry.object.storage_key))
    return SourceAuditReport(entries=tuple(entries), missing_current_sources=tuple(missing))


def select_repair_candidates(
    report: SourceAuditReport,
    *,
    delete_stale_versions: bool = False,
    min_age_hours: float = 24.0,
    now: datetime | None = None,
) -> list[SourceObject]:
    """Select safe cleanup candidates.

    Default repair removes only objects whose unit has already been deleted.
    Historical versions require explicit delete_stale_versions. Malformed and
    attached legacy objects are never selected automatically.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max(0.0, min_age_hours))
    allowed = {"orphan_unit", "orphan_legacy"}
    if delete_stale_versions:
        allowed.add("stale_version")

    selected: list[SourceObject] = []
    for entry in report.entries:
        if entry.status not in allowed:
            continue
        modified_at = entry.object.modified_at
        if modified_at is None:
            continue
        if modified_at.tzinfo is None:
            modified_at = modified_at.replace(tzinfo=timezone.utc)
        if modified_at <= cutoff:
            selected.append(entry.object)
    return selected


__all__ = [
    "ExpectedSource",
    "SourceAuditEntry",
    "SourceAuditReport",
    "classify_source_objects",
    "select_repair_candidates",
]
