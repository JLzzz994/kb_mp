from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config.settings import settings
from app.infrastructure.source_storage import LocalSourceStorage, MinioSourceStorage


class FakeMinio:
    def __init__(self) -> None:
        self.buckets: set[str] = set()
        self.objects: dict[tuple[str, str], bytes] = {}

    def bucket_exists(self, bucket: str) -> bool:
        return bucket in self.buckets

    def make_bucket(self, bucket: str) -> None:
        self.buckets.add(bucket)

    def fput_object(
        self,
        bucket: str,
        object_name: str,
        path: str,
        *,
        content_type: str,
    ) -> None:
        del content_type
        self.objects[(bucket, object_name)] = Path(path).read_bytes()

    def stat_object(self, bucket: str, object_name: str):
        if (bucket, object_name) not in self.objects:
            exc = RuntimeError("missing")
            exc.code = "NoSuchKey"  # type: ignore[attr-defined]
            raise exc
        return SimpleNamespace(object_name=object_name)

    def fget_object(self, bucket: str, object_name: str, path: str) -> None:
        Path(path).write_bytes(self.objects[(bucket, object_name)])

    def list_objects(self, bucket: str, *, prefix: str, recursive: bool):
        del recursive
        return [
            SimpleNamespace(object_name=name)
            for (stored_bucket, name) in self.objects
            if stored_bucket == bucket and name.startswith(prefix)
        ]

    def remove_objects(self, bucket: str, delete_objects):
        for delete in delete_objects:
            self.objects.pop((bucket, delete.object_name), None)
        return iter(())


@pytest.mark.asyncio
async def test_local_source_storage_is_versioned_and_materializable(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path))
    storage = LocalSourceStorage(prefix="sources")
    source = tmp_path / "upload.pdf"
    source.write_bytes(b"pdf-bytes")
    content_hash = "a" * 64

    archived = await storage.archive_temp_file(
        source,
        unit_code="KU-TEST-001",
        file_type="pdf",
        content_hash=content_hash,
    )

    assert source.exists() is False
    assert archived.backend == "local"
    assert archived.locator.endswith(f"KU-TEST-001/{content_hash}.pdf")

    materialized = await storage.materialize(
        unit_code="KU-TEST-001",
        file_type="pdf",
        content_hash=content_hash,
    )
    assert materialized is not None
    assert materialized.path.read_bytes() == b"pdf-bytes"
    assert materialized.cleanup_after_use is False

    await storage.delete_unit_sources("KU-TEST-001")
    assert materialized.path.exists() is False


@pytest.mark.asyncio
async def test_local_source_storage_reads_legacy_unit_code_file(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path))
    legacy = tmp_path / "KU-LEGACY.pdf"
    legacy.write_bytes(b"legacy")
    storage = LocalSourceStorage(prefix="sources")

    materialized = await storage.materialize(
        unit_code="KU-LEGACY",
        file_type="pdf",
        content_hash="b" * 64,
    )

    assert materialized is not None
    assert materialized.path == legacy


@pytest.mark.asyncio
async def test_minio_source_storage_uses_content_hash_version_key(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "runtime"))
    client = FakeMinio()
    storage = MinioSourceStorage(
        endpoint="minio:9000",
        bucket="kb-source-docs",
        prefix="sources",
        secure=False,
        client=client,
    )
    source = tmp_path / "manual.docx"
    source.write_bytes(b"docx-v1")
    content_hash = "c" * 64

    archived = await storage.archive_temp_file(
        source,
        unit_code="KU-TEST-002",
        file_type="docx",
        content_hash=content_hash,
    )

    object_name = f"sources/KU-TEST-002/{content_hash}.docx"
    assert archived.locator == f"kb-source-docs/{object_name}"
    assert client.objects[("kb-source-docs", object_name)] == b"docx-v1"
    assert source.exists() is False

    materialized = await storage.materialize(
        unit_code="KU-TEST-002",
        file_type="docx",
        content_hash=content_hash,
    )
    assert materialized is not None
    assert materialized.backend == "minio"
    assert materialized.path.read_bytes() == b"docx-v1"
    assert materialized.cleanup_after_use is True

    materialized.cleanup()
    assert materialized.path.exists() is False

    await storage.delete_unit_sources("KU-TEST-002")
    assert ("kb-source-docs", object_name) not in client.objects
