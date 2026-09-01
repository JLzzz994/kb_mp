"""Structured document models shared by parsers and chunkers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class DocumentBlock:
    text: str
    page_no: int | None = None
    block_type: str = "text"
    heading_level: int = 0
    bbox: tuple[int, int, int, int] | None = None


@dataclass(slots=True)
class ParsedDocument:
    text: str
    blocks: list[DocumentBlock] = field(default_factory=list)
    parser_name: str = "native"


@dataclass(slots=True)
class StructuredChunk:
    text: str
    index: int
    page_start: int | None = None
    page_end: int | None = None
    section_path: str = ""
    block_types: tuple[str, ...] = ()


__all__ = ["DocumentBlock", "ParsedDocument", "StructuredChunk"]
