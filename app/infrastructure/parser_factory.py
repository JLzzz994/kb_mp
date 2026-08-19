"""Format-Handler-Map：按扩展名路由解析器。"""

from __future__ import annotations

from pathlib import Path

from app.infrastructure.parsers.base_parser import BaseParser
from app.infrastructure.parsers.docx_parser import DocxParser
from app.infrastructure.parsers.markdown_parser import MarkdownParser
from app.infrastructure.parsers.pdf_parser import PDFParser
from app.infrastructure.parsers.txt_parser import TxtParser


class UnsupportedFormatError(Exception):
    """ParserFactory 不支持的扩展名。"""


class ParserFactory:
    SUPPORTED_EXTENSIONS = ("pdf", "md", "docx", "txt")

    def __init__(self) -> None:
        self._handlers: dict[str, BaseParser] = {
            "pdf": PDFParser(),
            "md": MarkdownParser(),
            "docx": DocxParser(),
            "txt": TxtParser(),
        }

    def parse(self, path: Path) -> str:
        """按 path.suffix 路由解析；不支持抛 UnsupportedFormatError。"""
        ext = path.suffix.lstrip(".").lower()
        handler = self._handlers.get(ext)
        if handler is None:
            raise UnsupportedFormatError(f"unsupported format: {ext or '(none)'}")
        return handler.parse(path)


_parser_factory = ParserFactory()


def get_parser_factory() -> ParserFactory:
    """FastAPI 依赖注入 + 模块级单例。"""
    return _parser_factory


__all__ = ["ParserFactory", "get_parser_factory", "UnsupportedFormatError"]
