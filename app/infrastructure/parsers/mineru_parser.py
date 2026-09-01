"""MinerU CLI adapter: document -> content_list.json -> structured blocks."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import pathlib

from app.config.settings import settings
from app.domain.document import DocumentBlock, ParsedDocument
from app.infrastructure.parsers.base_parser import ParseError


_AUXILIARY_TYPES = {
    "header",
    "footer",
    "page_number",
    "aside_text",
    "page_footnote",
    "page_header",
    "page_footer",
    "page_aside_text",
}


def _stringify(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                content = item.get("content") or item.get("text")
                if content:
                    parts.append(str(content))
        return "\n".join(part for part in parts if part).strip()
    return ""


def _block_text(item: dict) -> str:
    """Support MinerU legacy content_list and common v2-like payload fields."""
    for key in (
        "text",
        "content",
        "table_body",
        "code_body",
        "equation",
        "list_items",
    ):
        text = _stringify(item.get(key))
        if text:
            return text

    content = item.get("content")
    if isinstance(content, dict):
        for key in (
            "title_content",
            "paragraph_content",
            "math_content",
            "table_content",
            "code_content",
            "list_items",
        ):
            text = _stringify(content.get(key))
            if text:
                return text
    return ""


def _normalize_bbox(value: object) -> tuple[int, int, int, int] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        return tuple(int(float(v)) for v in value)  # type: ignore[return-value]
    except (TypeError, ValueError):
        return None


def parse_content_list(payload: object) -> list[DocumentBlock]:
    """Convert MinerU content_list output into reading-order blocks."""
    items: list[dict] = []
    if isinstance(payload, list):
        # legacy content_list: flat blocks; v2 may be page-grouped
        for value in payload:
            if not isinstance(value, dict):
                continue
            page_items = value.get("content") or value.get("items")
            if isinstance(page_items, list) and "page_idx" in value:
                for item in page_items:
                    if isinstance(item, dict):
                        merged = dict(item)
                        merged.setdefault("page_idx", value.get("page_idx"))
                        items.append(merged)
            else:
                items.append(value)
    elif isinstance(payload, dict):
        candidate = payload.get("content") or payload.get("items") or payload.get("pages")
        if isinstance(candidate, list):
            return parse_content_list(candidate)

    blocks: list[DocumentBlock] = []
    for item in items:
        block_type = str(item.get("type") or "text")
        if block_type in _AUXILIARY_TYPES:
            continue
        text = _block_text(item)
        if not text:
            continue

        raw_page = item.get("page_idx")
        try:
            page_no = int(raw_page) + 1 if raw_page is not None else None
        except (TypeError, ValueError):
            page_no = None

        raw_level = item.get("text_level")
        if raw_level is None and isinstance(item.get("content"), dict):
            raw_level = item["content"].get("level")
        try:
            heading_level = max(0, int(raw_level or 0))
        except (TypeError, ValueError):
            heading_level = 0

        blocks.append(
            DocumentBlock(
                text=text,
                page_no=page_no,
                block_type=block_type,
                heading_level=heading_level,
                bbox=_normalize_bbox(item.get("bbox")),
            )
        )
    return blocks


class MinerUParser:
    """Run MinerU CLI and read its structured content_list output."""

    def __init__(
        self,
        executable: str | None = None,
        backend: str | None = None,
        api_url: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self._executable = executable or settings.mineru_executable
        self._backend = backend if backend is not None else settings.mineru_backend
        self._api_url = api_url if api_url is not None else settings.mineru_api_url
        self._timeout = timeout_seconds or settings.mineru_timeout_seconds

    def available(self) -> bool:
        return shutil.which(self._executable) is not None

    def parse_document(self, path: pathlib.Path) -> ParsedDocument:
        if not self.available():
            raise ParseError(f"MinerU executable not found: {self._executable}", path)

        with tempfile.TemporaryDirectory(prefix="kb-mineru-") as temp_dir:
            output_dir = pathlib.Path(temp_dir)
            command = [self._executable, "-p", str(path), "-o", str(output_dir)]
            if self._api_url:
                command.extend(["--api-url", self._api_url])
            elif self._backend:
                command.extend(["-b", self._backend])

            env = os.environ.copy()
            if settings.mineru_model_source:
                env["MINERU_MODEL_SOURCE"] = settings.mineru_model_source

            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                    check=False,
                    env=env,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ParseError(f"MinerU execution failed: {path.name}", path) from exc

            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "")[-500:]
                raise ParseError(f"MinerU parse failed: {path.name}: {detail}", path)

            content_lists = sorted(output_dir.rglob("*_content_list.json"))
            if not content_lists:
                raise ParseError(f"MinerU content_list not found: {path.name}", path)

            try:
                payload = json.loads(content_lists[0].read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ParseError(f"MinerU content_list invalid: {path.name}", path) from exc

            blocks = parse_content_list(payload)
            if not blocks:
                raise ParseError(f"MinerU produced no readable blocks: {path.name}", path)
            text = "\n\n".join(block.text for block in blocks)
            return ParsedDocument(text=text, blocks=blocks, parser_name="mineru")


__all__ = ["MinerUParser", "parse_content_list"]
