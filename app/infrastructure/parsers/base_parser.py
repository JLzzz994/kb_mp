"""解析器基类 + ParseError 统一异常。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class ParseError(Exception):
    """解析失败统一异常。"""

    def __init__(self, message: str, file_path: Path) -> None:
        super().__init__(message)
        self.file_path = file_path


class BaseParser(ABC):
    @abstractmethod
    def parse(self, path: Path) -> str:
        """解析文件为纯文本。失败抛 ParseError。"""
        raise NotImplementedError


__all__ = ["BaseParser", "ParseError"]
