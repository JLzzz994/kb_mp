"""Helpers for reproducible ERP/WMS evaluation runs."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
from importlib import metadata
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_number}") from exc
            if not isinstance(item, dict):
                raise ValueError(f"expected object at {path}:{line_number}")
            rows.append(item)
    return rows


def dataset_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot_revision(root: Path) -> str | None:
    parts = root.parts
    for index, part in enumerate(parts[:-1]):
        if part == "snapshots":
            return parts[index + 1]
    return None


def model_config_fingerprint(model_path: str) -> dict:
    """Fingerprint model metadata + weight manifest without hashing multi-GB weights."""
    root = Path(model_path)
    candidates = (
        "config.json",
        "configuration.json",
        "modules.json",
        "sentence_bert_config.json",
        "config_sentence_transformers.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
    )
    digest = hashlib.sha256()
    files: list[str] = []
    if root.is_dir():
        for name in candidates:
            path = root / name
            if not path.is_file():
                continue
            files.append(name)
            digest.update(name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    weight_rows: list[tuple[str, int]] = []
    if root.is_dir():
        for pattern in ("*.safetensors", "*.bin", "*.pt", "*.pth"):
            for path in root.rglob(pattern):
                if path.is_file():
                    weight_rows.append((str(path.relative_to(root)), path.stat().st_size))
    weight_rows.sort()
    weight_digest = hashlib.sha256()
    for name, size in weight_rows:
        weight_digest.update(f"{name}:{size}\n".encode())

    return {
        "path": model_path,
        "exists": root.exists(),
        "snapshot_revision": _snapshot_revision(root),
        "metadata_files": files,
        "metadata_sha256": digest.hexdigest() if files else None,
        "weight_manifest_sha256": weight_digest.hexdigest() if weight_rows else None,
        "weight_file_count": len(weight_rows),
        "weight_bytes": sum(size for _, size in weight_rows),
        "weight_manifest_note": "filename+size manifest; not a full weight-content hash",
    }


def runtime_environment_fingerprint() -> dict:
    distributions = (
        "sentence-transformers",
        "FlagEmbedding",
        "pymilvus",
        "torch",
        "transformers",
        "numpy",
        "ragas",
        "openai",
    )
    versions: dict[str, str | None] = {}
    for distribution in distributions:
        try:
            versions[distribution] = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            versions[distribution] = None
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": versions,
    }


def current_git_sha() -> str:
    env_sha = os.getenv("GITHUB_SHA", "").strip()
    if env_sha:
        return env_sha
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def compare_named_metrics(
    current: dict[str, float | int],
    baseline: dict[str, float | int],
    metric_names: tuple[str, ...],
    *,
    tolerance: float = 0.0,
) -> dict:
    deltas: dict[str, float] = {}
    regressions: list[str] = []
    for metric in metric_names:
        current_value = float(current.get(metric, 0.0))
        baseline_value = float(baseline.get(metric, 0.0))
        delta = current_value - baseline_value
        deltas[metric] = delta
        if delta < -abs(tolerance):
            regressions.append(metric)
    return {
        "tolerance": abs(tolerance),
        "deltas": deltas,
        "regressions": regressions,
        "passed": not regressions,
    }


def compare_metric_summaries(
    current: dict[str, float | int],
    baseline: dict[str, float | int],
    *,
    tolerance: float = 0.0,
) -> dict:
    return compare_named_metrics(
        current,
        baseline,
        ("hit_at_k", "recall_at_k", "mrr"),
        tolerance=tolerance,
    )


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


__all__ = [
    "compare_metric_summaries",
    "compare_named_metrics",
    "current_git_sha",
    "dataset_sha256",
    "load_jsonl",
    "model_config_fingerprint",
    "runtime_environment_fingerprint",
    "write_json",
]
