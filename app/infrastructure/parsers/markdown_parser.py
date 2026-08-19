"""Markdown 解析：去除 HTML 标签后保留正文。"""

from __future__ import annotations

import re
from pathlib import Path

from app.infrastructure.parsers.base_parser import BaseParser


class MarkdownParser(BaseParser):
    _HTML_TAG = re.compile(r"<[^>]+>")

    def parse(self, path: Path) -> str:
        """演示期：读源文本 + 移除 HTML 标签（保留代码块 / 表格 / 公式原样）。"""
        return self._HTML_TAG.sub("", path.read_text(encoding="utf-8"))


__all__ = ["MarkdownParser"]
