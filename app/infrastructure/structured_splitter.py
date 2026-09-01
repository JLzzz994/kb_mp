"""Section/page-aware chunking for MinerU structured blocks."""

from __future__ import annotations

from app.config.settings import settings
from app.domain.document import DocumentBlock, ParsedDocument, StructuredChunk


class StructuredSplitter:
    """Merge reading-order blocks while preserving section path and page range."""

    def __init__(self, chunk_size: int | None = None, overlap: int | None = None) -> None:
        self._chunk_size = chunk_size or settings.structured_chunk_size
        self._overlap = overlap if overlap is not None else settings.structured_chunk_overlap

    def split(self, document: ParsedDocument) -> list[StructuredChunk]:
        if not document.blocks:
            text = document.text.strip()
            if not text:
                return []
            return [StructuredChunk(text=text, index=0)]

        section_stack: list[str] = []
        chunks: list[StructuredChunk] = []
        buffer: list[DocumentBlock] = []
        buffer_chars = 0
        current_section = ""

        def flush(*, keep_overlap: bool = True) -> None:
            nonlocal buffer, buffer_chars
            if not buffer:
                return
            text = "\n\n".join(block.text.strip() for block in buffer if block.text.strip()).strip()
            if not text:
                buffer = []
                buffer_chars = 0
                return
            pages = [block.page_no for block in buffer if block.page_no is not None]
            block_types = tuple(dict.fromkeys(block.block_type for block in buffer))
            chunks.append(
                StructuredChunk(
                    text=text,
                    index=len(chunks),
                    page_start=min(pages) if pages else None,
                    page_end=max(pages) if pages else None,
                    section_path=current_section,
                    block_types=block_types,
                )
            )
            buffer = self._overlap_tail(buffer) if keep_overlap else []
            buffer_chars = sum(len(block.text) for block in buffer)

        for block in document.blocks:
            text = block.text.strip()
            if not text:
                continue

            if block.heading_level > 0:
                flush(keep_overlap=False)
                level = min(block.heading_level, 6)
                section_stack[:] = section_stack[: level - 1]
                while len(section_stack) < level - 1:
                    section_stack.append("")
                if len(section_stack) == level - 1:
                    section_stack.append(text)
                else:
                    section_stack[level - 1] = text
                current_section = " / ".join(part for part in section_stack if part)
                # 标题也写入 chunk，让 embedding 保留章节语义。

            if buffer and buffer_chars + len(text) > self._chunk_size:
                flush()

            buffer.append(block)
            buffer_chars += len(text)

            # 大表格/代码等保护块即使超过 chunk size 也保持完整并立即 flush。
            if len(text) >= self._chunk_size or block.block_type in {"table", "code", "algorithm"}:
                flush()

        flush()
        return chunks

    def _overlap_tail(self, blocks: list[DocumentBlock]) -> list[DocumentBlock]:
        if self._overlap <= 0:
            return []
        kept: list[DocumentBlock] = []
        chars = 0
        for block in reversed(blocks):
            if block.heading_level > 0:
                continue
            kept.append(block)
            chars += len(block.text)
            if chars >= self._overlap:
                break
        kept.reverse()
        return kept


__all__ = ["StructuredSplitter"]
