"""MinerU structured parsing -> chunking -> batch vectorization tests."""

from __future__ import annotations

import pytest

from app.domain.document import DocumentBlock, ParsedDocument, StructuredChunk
from app.infrastructure.parsers.mineru_parser import parse_content_list
from app.infrastructure.structured_splitter import StructuredSplitter
from app.services.knowledge_import_service import _vectorize_and_upsert


def test_parse_mineru_content_list_preserves_page_heading_and_table() -> None:
    payload = [
        {
            "type": "text",
            "text": "库存管理",
            "text_level": 1,
            "page_idx": 0,
            "bbox": [10, 20, 500, 60],
        },
        {
            "type": "text",
            "text": "可用库存会受到占用和锁定状态影响。",
            "page_idx": 0,
            "bbox": [10, 70, 900, 120],
        },
        {
            "type": "table",
            "table_body": "| 状态 | 含义 |\n|---|---|\n| 锁定 | 不可销售 |",
            "page_idx": 1,
            "bbox": [20, 100, 950, 600],
        },
        {
            "type": "page_number",
            "text": "2",
            "page_idx": 1,
        },
    ]
    blocks = parse_content_list(payload)
    assert len(blocks) == 3
    assert blocks[0].heading_level == 1
    assert blocks[0].page_no == 1
    assert blocks[2].block_type == "table"
    assert blocks[2].page_no == 2


def test_structured_splitter_preserves_section_and_page_range() -> None:
    document = ParsedDocument(
        text="库存管理\n可用库存说明\n库存异常\n排查步骤",
        parser_name="mineru",
        blocks=[
            DocumentBlock("库存管理", page_no=1, block_type="text", heading_level=1),
            DocumentBlock("可用库存说明", page_no=1),
            DocumentBlock("库存异常", page_no=2, block_type="text", heading_level=2),
            DocumentBlock("排查步骤", page_no=2),
        ],
    )
    chunks = StructuredSplitter(chunk_size=100, overlap=0).split(document)
    assert len(chunks) == 2
    assert chunks[0].section_path == "库存管理"
    assert chunks[0].page_start == 1
    assert chunks[1].section_path == "库存管理 / 库存异常"
    assert chunks[1].page_start == 2
    assert chunks[1].page_end == 2


@pytest.mark.asyncio
async def test_vectorize_batches_chunks_and_upserts_metadata() -> None:
    class Embedding:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        async def embed_batch(self, texts: list[str]) -> list[list[float]]:
            self.calls.append(texts)
            return [[float(i), 0.5] for i, _ in enumerate(texts)]

    class Milvus:
        def __init__(self) -> None:
            self.rows: list[dict] = []

        async def upsert_chunks(self, rows: list[dict]) -> None:
            self.rows = rows

    embedding = Embedding()
    milvus = Milvus()
    chunks = [
        StructuredChunk(
            text="可用库存说明",
            index=0,
            page_start=3,
            page_end=3,
            section_path="库存 / 可用库存",
            block_types=("text",),
        ),
        StructuredChunk(
            text="库存异常排查",
            index=1,
            page_start=4,
            page_end=5,
            section_path="库存 / 异常排查",
            block_types=("text", "table"),
        ),
    ]

    await _vectorize_and_upsert(
        milvus=milvus,
        embedding=embedding,
        session_factory=lambda: None,
        unit_id=42,
        title="WMS 库存手册",
        category="pdf",
        source_file_name="wms-inventory.pdf",
        chunks=chunks,
    )

    assert embedding.calls == [["可用库存说明", "库存异常排查"]]
    assert len(milvus.rows) == 2
    assert milvus.rows[0]["chunk_id"] == "42:0"
    assert milvus.rows[1]["page_start"] == 4
    assert milvus.rows[1]["page_end"] == 5
    assert milvus.rows[1]["section_path"] == "库存 / 异常排查"
    assert milvus.rows[1]["source_file_name"] == "wms-inventory.pdf"
