"""Real MinIO network smoke test.

Skipped from ordinary pytest. The dedicated GitHub Actions job starts a real MinIO
container and enables this test with RUN_MINIO_INTEGRATION=1.
"""

from __future__ import annotations

import os
import uuid

import pytest

from app.config.settings import settings
from app.infrastructure.source_storage import MinioSourceStorage

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MINIO_INTEGRATION") != "1",
    reason="requires a real MinIO endpoint",
)


@pytest.mark.asyncio
async def test_real_minio_archive_materialize_and_delete(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "runtime"))
    unit_code = f"KU-CI-{uuid.uuid4().hex[:10].upper()}"
    content_hash = uuid.uuid4().hex * 2
    source = tmp_path / "wms-guide.pdf"
    source_bytes = b"%PDF-1.4\nreal-minio-source-smoke\n"
    source.write_bytes(source_bytes)

    storage = MinioSourceStorage(
        endpoint=os.environ["SOURCE_MINIO_ENDPOINT"],
        access_key=os.environ["SOURCE_MINIO_ACCESS_KEY"],
        secret_key=os.environ["SOURCE_MINIO_SECRET_KEY"],
        bucket=os.environ["SOURCE_MINIO_BUCKET"],
        secure=False,
        prefix="sources",
    )

    archived = await storage.archive_temp_file(
        source,
        unit_code=unit_code,
        file_type="pdf",
        content_hash=content_hash,
    )
    expected_object = f"sources/{unit_code}/{content_hash}.pdf"
    assert archived.backend == "minio"
    assert archived.locator == f"{os.environ['SOURCE_MINIO_BUCKET']}/{expected_object}"
    assert source.exists() is False

    materialized = await storage.materialize(
        unit_code=unit_code,
        file_type="pdf",
        content_hash=content_hash,
    )
    assert materialized is not None
    assert materialized.backend == "minio"
    assert materialized.path.read_bytes() == source_bytes
    assert materialized.cleanup_after_use is True

    materialized.cleanup()
    assert materialized.path.exists() is False

    await storage.delete_unit_sources(unit_code)
    missing = await storage.materialize(
        unit_code=unit_code,
        file_type="pdf",
        content_hash=content_hash,
    )
    assert missing is None
