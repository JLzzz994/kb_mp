"""TXT 解析器：UTF-8 优先，失败回退 GBK。"""

from __future__ import annotations

from pathlib import Path

from app.infrastructure.parsers.base_parser import BaseParser, ParseError


class TxtParser(BaseParser):
    def parse(self, path: Path) -> str:
        """UTF-8 → GBK 回退；都失败抛 ParseError。"""
        raw = path.read_bytes()
        # 1. UTF-8
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            pass
        # 2. GBK 回退（Windows 中文 TXT 兼容）
        try:
            return raw.decode("gbk")
        except UnicodeDecodeError as exc:
            raise ParseError(f"decode failed: {path.name}", path) from exc


__all__ = ["TxtParser"]
