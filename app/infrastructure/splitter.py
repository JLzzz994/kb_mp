"""Splitter：保护块占位符 + RecursiveCharacterTextSplitter。"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass


@dataclass(slots=True)
class Chunk:
    text: str
    index: int  # 在原文档中的顺序


class Splitter:
    """文本切片器。

    流程：
    1. 抽取保护块（代码块 / inline_code / 表格 / 公式）→ UUID 占位符
    2. 按 Markdown 标题 (#{1,6}) 粗切
    3. 超长用 RecursiveCharacterTextSplitter 细切 + 短块合并
    4. 从后往前还原占位符内容
    """

    CHUNK_MAX_SIZE = 1000
    CHUNK_SIZE = 600
    CHUNK_OVERLAP = 100
    SEPARATORS = ["\n\n", "\n", "。", "！", "？"]

    PROTECTED_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
        ("code_block", re.compile(r"```[\s\S]*?```", re.MULTILINE)),
        ("inline_code", re.compile(r"`[^`]+`")),
        ("table", re.compile(r"((?:\|[^\n]+\|\n)+)", re.MULTILINE)),
        ("formula_block", re.compile(r"\$\$[\s\S]*?\$\$", re.MULTILINE)),
        ("formula_inline", re.compile(r"\$[^$\n]+\$")),
    ]

    TITLE_PATTERN = re.compile(r"^#{1,6}\s+.+$", re.MULTILINE)

    def __init__(self) -> None:
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter

            self._recursive = RecursiveCharacterTextSplitter(
                chunk_size=self.CHUNK_SIZE,
                chunk_overlap=self.CHUNK_OVERLAP,
                separators=self.SEPARATORS,
            )
        except ImportError:
            # langchain-text-splitters 未装：退化为简单固定切片（不会保护块细切）
            self._recursive = None

    def split(self, text: str, title: str = "") -> list[Chunk]:
        """主入口。"""
        if not text.strip():
            return []
        protected_map: dict[str, str] = {}
        masked = self._extract_protected_blocks(text, protected_map)
        coarse_chunks = self._split_by_titles(masked, title=title)
        refined = self._refine_chunks(coarse_chunks)
        for chunk in refined:
            chunk.text = self._restore_placeholders(chunk.text, protected_map)
        return [Chunk(text=c.text, index=i) for i, c in enumerate(refined)]

    def _extract_protected_blocks(self, text: str, protected_map: dict[str, str]) -> str:
        """将保护块替换为 UUID 占位符（原文存 protected_map）。"""
        result = text
        for _kind, pattern in self.PROTECTED_PATTERNS:
            new_parts: list[str] = []
            last = 0
            for match in pattern.finditer(result):
                new_parts.append(result[last : match.start()])
                original = match.group(0)
                placeholder = f"⟦{uuid.uuid4().hex[:8]}⟧"
                protected_map[placeholder] = original
                new_parts.append(placeholder)
                last = match.end()
            new_parts.append(result[last:])
            result = "".join(new_parts)
        return result

    def _split_by_titles(self, text: str, title: str) -> list[Chunk]:
        """按 Markdown 标题粗切；无标题整文一块。"""
        if not self.TITLE_PATTERN.search(text):
            return [Chunk(text=text.strip(), index=0)] if text.strip() else []
        parts = self.TITLE_PATTERN.split(text)
        return [Chunk(text=p.strip(), index=i) for i, p in enumerate(parts) if p.strip()]

    def _refine_chunks(self, chunks: list[Chunk]) -> list[Chunk]:
        """短块合并 + 超长用 RecursiveCharacterTextSplitter 细切。"""
        refined: list[Chunk] = []
        buffer = ""
        for chunk in chunks:
            if len(chunk.text) <= self.CHUNK_SIZE:
                buffer = (buffer + "\n\n" + chunk.text) if buffer else chunk.text
                if len(buffer) >= self.CHUNK_SIZE:
                    refined.append(Chunk(text=buffer, index=0))
                    buffer = ""
            else:
                if buffer:
                    refined.append(Chunk(text=buffer, index=0))
                    buffer = ""
                if self._recursive is not None:
                    pieces = self._recursive.split_text(chunk.text)
                else:
                    pieces = [
                        chunk.text[i : i + self.CHUNK_SIZE]
                        for i in range(0, len(chunk.text), self.CHUNK_SIZE)
                    ]
                for p in pieces:
                    refined.append(Chunk(text=p, index=0))
        if buffer:
            refined.append(Chunk(text=buffer, index=0))
        return refined

    def _restore_placeholders(self, text: str, protected_map: dict[str, str]) -> str:
        """还原占位符（从后往前避免错位）。"""
        for placeholder, original in sorted(protected_map.items(), reverse=True):
            text = text.replace(placeholder, original)
        return text


__all__ = ["Splitter", "Chunk"]
