"""Word 解析：python-docx。"""

from __future__ import annotations

from pathlib import Path

from app.infrastructure.parsers.base_parser import BaseParser, ParseError


class DocxParser(BaseParser):
    def parse(self, path: Path) -> str:
        """逐段提取 docx 段落文本（双换行拼接）。"""
        try:
            from docx import Document

            doc = Document(str(path))
        except Exception as exc:
            raise ParseError(f"DOCX open failed: {path.name}", path) from exc
        parts = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(parts)


__all__ = ["DocxParser"]
