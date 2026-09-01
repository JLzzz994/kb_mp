"""Format-Handler-Map：按扩展名路由原生解析器，并可接入 MinerU。"""

from __future__ import annotations

import re
from pathlib import Path

from loguru import logger

from app.config.settings import settings
from app.domain.document import DocumentBlock, ParsedDocument
from app.infrastructure.parsers.base_parser import BaseParser, ParseError
from app.infrastructure.parsers.docx_parser import DocxParser
from app.infrastructure.parsers.markdown_parser import MarkdownParser
from app.infrastructure.parsers.mineru_parser import MinerUParser
from app.infrastructure.parsers.pdf_parser import PDFParser
from app.infrastructure.parsers.txt_parser import TxtParser


class UnsupportedFormatError(Exception):
    """ParserFactory 不支持的扩展名。"""


class ParserFactory:
    SUPPORTED_EXTENSIONS = ("pdf", "md", "docx", "txt")
    MINERU_EXTENSIONS = {"pdf", "docx"}

    def __init__(self, mineru_parser: MinerUParser | None = None) -> None:
        self._handlers: dict[str, BaseParser] = {
            "pdf": PDFParser(),
            "md": MarkdownParser(),
            "docx": DocxParser(),
            "txt": TxtParser(),
        }
        self._mineru = mineru_parser or MinerUParser()

    def parse(self, path: Path) -> str:
        """兼容旧调用：返回纯文本。"""
        return self.parse_document(path).text

    def parse_document(self, path: Path) -> ParsedDocument:
        """优先 MinerU 结构化解析，auto 模式失败时降级原生 parser。"""
        ext = path.suffix.lstrip(".").lower()
        handler = self._handlers.get(ext)
        if handler is None:
            raise UnsupportedFormatError(f"unsupported format: {ext or '(none)'}")

        backend = settings.document_parser_backend.lower()
        use_mineru = backend in {"auto", "mineru"} and ext in self.MINERU_EXTENSIONS
        if use_mineru:
            try:
                return self._mineru.parse_document(path)
            except ParseError as exc:
                if backend == "mineru":
                    raise
                logger.warning("parser.mineru.fallback file={} error={}", path.name, exc)

        text = handler.parse(path)
        return ParsedDocument(
            text=text,
            blocks=_native_blocks(text),
            parser_name=f"native_{ext}",
        )


def _native_blocks(text: str) -> list[DocumentBlock]:
    """原生解析也尽量识别 Markdown 风格标题，统一进入结构化 chunker。"""
    blocks: list[DocumentBlock] = []
    for raw in re.split(r"\n\s*\n", text):
        value = raw.strip()
        if not value:
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", value)
        if heading:
            blocks.append(
                DocumentBlock(
                    text=heading.group(2).strip(),
                    block_type="title",
                    heading_level=len(heading.group(1)),
                )
            )
        else:
            blocks.append(DocumentBlock(text=value))
    return blocks


_parser_factory = ParserFactory()


def get_parser_factory() -> ParserFactory:
    """FastAPI 依赖注入 + 模块级单例。"""
    return _parser_factory


__all__ = ["ParserFactory", "get_parser_factory", "UnsupportedFormatError"]
