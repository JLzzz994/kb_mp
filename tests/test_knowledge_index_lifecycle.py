from __future__ import annotations

import pytest

from app.config.settings import settings
from app.domain.document import DocumentBlock, ParsedDocument
from app.infrastructure.database import KnowledgeUnitRecord
from app.infrastructure.file_storage import persist_unit_source
from app.infrastructure.structured_splitter import StructuredSplitter
from app.services.knowledge_index_service import KnowledgeIndexService
from app.services.knowledge_unit_service import _compute_content_hash, _gen_unit_code


class FakeEmbedding:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [[float(index), 0.5] for index, _ in enumerate(texts)]


class FakeMilvus:
    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []
        self.rows: list[dict] = []
        self.count = 0
        self.metadata_updates: list[dict] = []

    async def delete_by_unit_ids(self, unit_ids: list[int]) -> None:
        self.events.append(("delete", list(unit_ids)))

    async def upsert_chunks(self, rows: list[dict]) -> None:
        self.rows = rows
        self.count = len(rows)
        self.events.append(("upsert", len(rows)))

    async def count_by_unit_id(self, unit_id: int) -> int:
        self.events.append(("count", unit_id))
        return self.count

    async def update_unit_metadata(
        self,
        unit_id: int,
        *,
        title: str,
        category: str | None,
        source_file_name: str | None,
    ) -> int:
        self.metadata_updates.append(
            {
                "unit_id": unit_id,
                "title": title,
                "category": category,
                "source_file_name": source_file_name,
            }
        )
        return self.count


async def _create_unit(
    db_session,
    seeded_admin,
    *,
    content: str,
    file_type: str | None = None,
) -> KnowledgeUnitRecord:
    unit = KnowledgeUnitRecord(
        unit_code=_gen_unit_code(),
        title="WMS 库存手册",
        content=content,
        category="wms",
        source_file_name="wms.pdf",
        file_type=file_type,
        content_hash=_compute_content_hash(content),
        status="active",
        creator_id=seeded_admin["user_id"],
    )
    db_session.add(unit)
    await db_session.commit()
    await db_session.refresh(unit)
    return unit


@pytest.mark.asyncio
async def test_rebuild_only_current_unit_and_replaces_old_chunks(db_session, seeded_admin) -> None:
    content = "# 库存管理\n\n可用库存说明。\n\n## 异常排查\n\n检查库存同步任务和占用锁定。"
    unit = await _create_unit(db_session, seeded_admin, content=content)
    embedding = FakeEmbedding()
    milvus = FakeMilvus()
    service = KnowledgeIndexService(
        db_session,
        embedding=embedding,
        milvus=milvus,
        splitter=StructuredSplitter(chunk_size=40, overlap=0),
    )

    result = await service.rebuild_unit(unit.id)

    assert result.configured is True
    assert result.consistent is True
    assert result.chunk_count == len(milvus.rows)
    assert len(milvus.rows) >= 2
    assert milvus.events[0] == ("delete", [unit.id])
    assert milvus.events[1][0] == "upsert"
    assert embedding.calls and embedding.calls[0]

    generation = unit.content_hash[:12]
    assert all(row["chunk_id"].startswith(f"{unit.id}:{generation}:") for row in milvus.rows)
    assert any(row["section_path"] == "库存管理 / 异常排查" for row in milvus.rows)

    await db_session.refresh(unit)
    assert unit.status == "active"


@pytest.mark.asyncio
async def test_metadata_sync_does_not_reembed_existing_chunks(db_session, seeded_admin) -> None:
    unit = await _create_unit(db_session, seeded_admin, content="库存说明")
    milvus = FakeMilvus()
    milvus.count = 3
    service = KnowledgeIndexService(db_session, embedding=None, milvus=milvus)

    result = await service.sync_metadata(unit.id)

    assert result.chunk_count == 3
    assert result.consistent is True
    assert milvus.metadata_updates == [
        {
            "unit_id": unit.id,
            "title": "WMS 库存手册",
            "category": "wms",
            "source_file_name": "wms.pdf",
        }
    ]


@pytest.mark.asyncio
async def test_delete_vectors_before_db_delete_can_reuse_cleanup(db_session, seeded_admin) -> None:
    unit = await _create_unit(db_session, seeded_admin, content="售后逆向流程")
    milvus = FakeMilvus()
    service = KnowledgeIndexService(db_session, embedding=FakeEmbedding(), milvus=milvus)

    await service.delete_units([unit.id])

    assert milvus.events == [("delete", [unit.id])]


@pytest.mark.asyncio
async def test_index_status_detects_missing_chunks(db_session, seeded_admin) -> None:
    unit = await _create_unit(db_session, seeded_admin, content="订单审核规则")
    milvus = FakeMilvus()
    service = KnowledgeIndexService(db_session, embedding=FakeEmbedding(), milvus=milvus)

    status = await service.get_status(unit.id)

    assert status.configured is True
    assert status.chunk_count == 0
    assert status.consistent is False
    assert status.detail == "index requires rebuild"


@pytest.mark.asyncio
async def test_rebuild_prefers_matching_archived_source_structure(
    db_session,
    seeded_admin,
    tmp_path,
    monkeypatch,
) -> None:
    content = "库存管理\n\n可用库存说明。"
    unit = await _create_unit(
        db_session,
        seeded_admin,
        content=content,
        file_type="pdf",
    )
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path))
    temp_source = tmp_path / "upload.pdf"
    temp_source.write_bytes(b"demo-pdf")
    persist_unit_source(temp_source, unit.unit_code)

    class FakeParserFactory:
        def parse_document(self, _path):
            return ParsedDocument(
                text=content,
                parser_name="fake_source",
                blocks=[
                    DocumentBlock(
                        text="库存管理",
                        page_no=3,
                        block_type="text",
                        heading_level=1,
                    ),
                    DocumentBlock(
                        text="可用库存说明。",
                        page_no=3,
                        block_type="text",
                    ),
                ],
            )

    milvus = FakeMilvus()
    service = KnowledgeIndexService(
        db_session,
        embedding=FakeEmbedding(),
        milvus=milvus,
        parser_factory=FakeParserFactory(),
        splitter=StructuredSplitter(chunk_size=100, overlap=0),
    )

    result = await service.rebuild_unit(unit.id)

    assert result.consistent is True
    assert len(milvus.rows) == 1
    assert milvus.rows[0]["page_start"] == 3
    assert milvus.rows[0]["page_end"] == 3
    assert milvus.rows[0]["section_path"] == "库存管理"
