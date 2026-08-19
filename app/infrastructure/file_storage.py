"""本地文件存储：storage/uploads/{uuid}.{ext}。"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from app.config.settings import settings


def get_storage_dir() -> Path:
    """本地存储目录（settings.storage_dir，默认 ./storage/uploads）。"""
    p = Path(settings.storage_dir).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_upload(filename: str, content: bytes) -> Path:
    """保存上传文件 → 返回落盘路径（uuid + 原扩展名）。"""
    ext = Path(filename).suffix.lstrip(".").lower()
    target = get_storage_dir() / f"{uuid.uuid4().hex}.{ext}"
    target.write_bytes(content)
    return target


def remove_file(path: Path | str) -> None:
    """删除落盘文件（不存在不报错）。"""
    try:
        Path(path).unlink(missing_ok=True)
    except (OSError, TypeError):
        pass


def move_to(src: Path | str, dst_dir: Path | str) -> Path:
    """移动文件到目标目录（用于归档等场景，演示期未使用）。"""
    src_p = Path(src)
    dst_p = Path(dst_dir)
    dst_p.mkdir(parents=True, exist_ok=True)
    target = dst_p / src_p.name
    shutil.move(str(src_p), str(target))
    return target


__all__ = ["get_storage_dir", "save_upload", "remove_file", "move_to"]
