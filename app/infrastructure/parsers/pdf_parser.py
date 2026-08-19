"""PDF 解析：pypdf。"""

from __future__ import annotations

from pathlib import Path

from app.infrastructure.parsers.base_parser import BaseParser, ParseError


class PDFParser(BaseParser):
    def parse(self, path: Path) -> str:
        """pypdf 逐页 extract_text()，双换行拼接。"""
        try:
            import pypdf

            reader = pypdf.PdfReader(str(path))
        except Exception as exc:
            raise ParseError(f"PDF open failed: {path.name}", path) from exc
        parts: list[str] = []
        for page in reader.pages:
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            if text:
                parts.append(text)
        return "\n\n".join(parts)


__all__ = ["PDFParser"]
