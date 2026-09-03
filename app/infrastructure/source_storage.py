"""Versioned product-document source storage: local filesystem or MinIO."""

from __future__ import annotations

import asyncio
import mimetypes
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from app.config.settings import settings
from app.infrastructure.file_storage import get_storage_dir, remove_file


@dataclass(slots=True)
class SourceArchiveResult:
    backend: str
    locator: str


@dataclass(slots=True)
class MaterializedSource:
    path: Path
    backend: str
    locator: str
    cleanup_after_use: bool = False

    def cleanup(self) -> None:
        if self.cleanup_after_use:
            remove_file(self.path)


@dataclass(slots=True)
class SourceObject:
    backend: str
    storage_key: str
    locator: str
    unit_code: str | None
    content_hash: str | None
    file_type: str | None
    size: int | None = None
    modified_at: datetime | None = None
    legacy: bool = False
    malformed: bool = False


class SourceStorage(Protocol):
    backend_name: str

    async def archive_temp_file(
        self,
        path: Path | str,
        *,
        unit_code: str,
        file_type: str | None,
        content_hash: str,
    ) -> SourceArchiveResult: ...

    async def materialize(
        self,
        *,
        unit_code: str,
        file_type: str | None,
        content_hash: str | None,
    ) -> MaterializedSource | None: ...

    async def delete_unit_sources(self, unit_code: str) -> None: ...

    async def list_source_objects(self) -> list[SourceObject]: ...

    async def delete_source_objects(self, objects: list[SourceObject]) -> None: ...


def _extension(file_type: str | None, path: Path | None = None) -> str:
    if file_type:
        return file_type.lower().lstrip(".")
    if path is not None:
        return path.suffix.lower().lstrip(".")
    return ""


def _is_content_hash(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdefABCDEF" for char in value)


class LocalSourceStorage:
    backend_name = "local"

    def __init__(self, *, prefix: str | None = None) -> None:
        self._prefix = (prefix or settings.source_storage_prefix).strip("/") or "sources"

    def _versioned_path(self, unit_code: str, content_hash: str, ext: str) -> Path:
        suffix = f".{ext}" if ext else ""
        return get_storage_dir() / self._prefix / unit_code / f"{content_hash}{suffix}"

    def _legacy_path(self, unit_code: str, ext: str) -> Path:
        suffix = f".{ext}" if ext else ""
        return get_storage_dir() / f"{unit_code}{suffix}"

    async def archive_temp_file(
        self,
        path: Path | str,
        *,
        unit_code: str,
        file_type: str | None,
        content_hash: str,
    ) -> SourceArchiveResult:
        src = Path(path)
        ext = _extension(file_type, src)
        target = self._versioned_path(unit_code, content_hash, ext)

        def _move() -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                target.unlink()
            shutil.move(str(src), str(target))

        await asyncio.to_thread(_move)
        return SourceArchiveResult(backend=self.backend_name, locator=str(target))

    async def materialize(
        self,
        *,
        unit_code: str,
        file_type: str | None,
        content_hash: str | None,
    ) -> MaterializedSource | None:
        ext = _extension(file_type)
        if content_hash:
            versioned = self._versioned_path(unit_code, content_hash, ext)
            if versioned.exists():
                return MaterializedSource(
                    path=versioned,
                    backend=self.backend_name,
                    locator=str(versioned),
                )

        # Backward compatibility for sources archived before versioned storage.
        legacy = self._legacy_path(unit_code, ext)
        if legacy.exists():
            return MaterializedSource(
                path=legacy,
                backend=self.backend_name,
                locator=str(legacy),
            )
        return None

    async def delete_unit_sources(self, unit_code: str) -> None:
        root = get_storage_dir()
        version_dir = root / self._prefix / unit_code

        def _delete() -> None:
            shutil.rmtree(version_dir, ignore_errors=True)
            for legacy in root.glob(f"{unit_code}.*"):
                remove_file(legacy)

        await asyncio.to_thread(_delete)

    async def list_source_objects(self) -> list[SourceObject]:
        root = get_storage_dir()
        version_root = root / self._prefix

        def _list() -> list[SourceObject]:
            objects: list[SourceObject] = []
            if version_root.exists():
                for path in sorted(version_root.glob("*/*")):
                    if not path.is_file():
                        continue
                    relative = path.relative_to(version_root)
                    unit_code = relative.parts[0] if len(relative.parts) >= 2 else None
                    stem = path.stem
                    stat = path.stat()
                    objects.append(
                        SourceObject(
                            backend=self.backend_name,
                            storage_key=str(path.relative_to(root)),
                            locator=str(path),
                            unit_code=unit_code,
                            content_hash=stem if _is_content_hash(stem) else None,
                            file_type=path.suffix.lstrip(".").lower() or None,
                            size=stat.st_size,
                            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                            malformed=unit_code is None or not _is_content_hash(stem),
                        )
                    )

            # Only KU-* is a legacy archive. UUID upload temp files must not be audited.
            for path in sorted(root.glob("KU-*.*")):
                if not path.is_file():
                    continue
                stat = path.stat()
                objects.append(
                    SourceObject(
                        backend=self.backend_name,
                        storage_key=path.name,
                        locator=str(path),
                        unit_code=path.stem,
                        content_hash=None,
                        file_type=path.suffix.lstrip(".").lower() or None,
                        size=stat.st_size,
                        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                        legacy=True,
                    )
                )
            return objects

        return await asyncio.to_thread(_list)

    async def delete_source_objects(self, objects: list[SourceObject]) -> None:
        root = get_storage_dir().resolve()

        def _delete() -> None:
            for item in objects:
                if item.backend != self.backend_name:
                    raise ValueError(f"cannot delete {item.backend} object with local storage")
                path = (root / item.storage_key).resolve()
                if not path.is_relative_to(root):
                    raise ValueError(f"source object escapes storage root: {item.storage_key}")
                path.unlink(missing_ok=True)
                parent = path.parent
                if parent != root and parent != root / self._prefix:
                    try:
                        parent.rmdir()
                    except OSError:
                        pass

        await asyncio.to_thread(_delete)


class MinioSourceStorage:
    backend_name = "minio"

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
        secure: bool | None = None,
        prefix: str | None = None,
        client=None,
    ) -> None:
        endpoint_value = endpoint or settings.source_minio_endpoint
        parsed = urlparse(endpoint_value if "://" in endpoint_value else f"http://{endpoint_value}")
        self._endpoint = parsed.netloc or parsed.path
        inferred_secure = parsed.scheme == "https"
        self._secure = settings.source_minio_secure if secure is None else secure
        if "://" in endpoint_value and secure is None:
            self._secure = inferred_secure

        self._bucket = bucket or settings.source_minio_bucket
        self._prefix = (prefix or settings.source_storage_prefix).strip("/") or "sources"
        if client is None:
            from minio import Minio

            client = Minio(
                self._endpoint,
                access_key=access_key or settings.source_minio_access_key,
                secret_key=secret_key or settings.source_minio_secret_key,
                secure=self._secure,
            )
        self._client = client

    def _object_name(self, unit_code: str, content_hash: str, ext: str) -> str:
        suffix = f".{ext}" if ext else ""
        return f"{self._prefix}/{unit_code}/{content_hash}{suffix}"

    def _ensure_bucket_sync(self) -> None:
        if self._client.bucket_exists(self._bucket):
            return
        try:
            self._client.make_bucket(self._bucket)
        except Exception:
            # Another replica may have created it between exists() and make_bucket().
            if not self._client.bucket_exists(self._bucket):
                raise

    async def archive_temp_file(
        self,
        path: Path | str,
        *,
        unit_code: str,
        file_type: str | None,
        content_hash: str,
    ) -> SourceArchiveResult:
        src = Path(path)
        ext = _extension(file_type, src)
        object_name = self._object_name(unit_code, content_hash, ext)
        content_type = mimetypes.guess_type(src.name)[0] or "application/octet-stream"

        def _upload() -> None:
            self._ensure_bucket_sync()
            self._client.fput_object(
                self._bucket,
                object_name,
                str(src),
                content_type=content_type,
            )

        await asyncio.to_thread(_upload)
        remove_file(src)
        return SourceArchiveResult(
            backend=self.backend_name,
            locator=f"{self._bucket}/{object_name}",
        )

    async def materialize(
        self,
        *,
        unit_code: str,
        file_type: str | None,
        content_hash: str | None,
    ) -> MaterializedSource | None:
        if not content_hash:
            return None
        ext = _extension(file_type)
        object_name = self._object_name(unit_code, content_hash, ext)

        def _download() -> Path | None:
            try:
                self._client.stat_object(self._bucket, object_name)
            except Exception as exc:
                code = getattr(exc, "code", "")
                if code in {
                    "NoSuchKey",
                    "NoSuchObject",
                    "NoSuchBucket",
                    "XMinioInvalidObjectName",
                }:
                    return None
                raise

            temp_dir = get_storage_dir() / ".materialized"
            temp_dir.mkdir(parents=True, exist_ok=True)
            suffix = f".{ext}" if ext else ""
            target = temp_dir / f"{uuid.uuid4().hex}{suffix}"
            self._client.fget_object(self._bucket, object_name, str(target))
            return target

        target = await asyncio.to_thread(_download)
        if target is None:
            return None
        return MaterializedSource(
            path=target,
            backend=self.backend_name,
            locator=f"{self._bucket}/{object_name}",
            cleanup_after_use=True,
        )

    async def delete_unit_sources(self, unit_code: str) -> None:
        prefix = f"{self._prefix}/{unit_code}/"

        def _delete() -> None:
            from minio.deleteobjects import DeleteObject

            objects = list(self._client.list_objects(self._bucket, prefix=prefix, recursive=True))
            if not objects:
                return
            errors = list(
                self._client.remove_objects(
                    self._bucket,
                    (DeleteObject(obj.object_name) for obj in objects),
                )
            )
            if errors:
                raise RuntimeError(f"MinIO delete failed: {errors[0]}")

        await asyncio.to_thread(_delete)


def build_source_storage() -> SourceStorage:
    backend = settings.source_storage_backend.strip().lower()
    if backend == "local":
        return LocalSourceStorage()
    if backend == "minio":
        return MinioSourceStorage()
    raise ValueError(f"Unsupported SOURCE_STORAGE_BACKEND: {settings.source_storage_backend}")


__all__ = [
    "LocalSourceStorage",
    "MaterializedSource",
    "MinioSourceStorage",
    "SourceArchiveResult",
    "SourceObject",
    "SourceStorage",
    "build_source_storage",
]
