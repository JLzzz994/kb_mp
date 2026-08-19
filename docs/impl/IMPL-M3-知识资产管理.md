# IMPL-M3 — 知识资产管理（Python 方法级实现蓝图）

| 项目 | 内容 |
| --- | --- |
| 文档版本 | V1.0 |
| 阶段 | P1 |
| 编写依据 | [Spec M3](../specs/M3-知识资产管理.md) |
| 范围 | 解析 / 切片 / 导入 / 单元 CRUD / 鉴权接口完整方法 + pytest |

---

## 1. 文件清单

```
app/
├── api/
│   ├── routers/knowledge_router.py
│   └── schemas/{knowledge_unit,knowledge_import,permission}_schema.py
├── domain/{knowledge_unit,unit_permission}.py
├── services/
│   ├── knowledge_import_service.py
│   ├── knowledge_unit_service.py
│   └── knowledge_permission_service.py
├── repositories/{knowledge_unit,unit_permission}_repository.py
└── infrastructure/
    ├── parser_factory.py
    ├── parsers/{base,pdf,docx,markdown,txt}_parser.py
    ├── splitter.py
    ├── milvus_gateway.py
    ├── file_storage.py
    ├── embedding.py                 # 新增（C2 修复）：EmbeddingService 封装 OpenAI Embeddings
    └── redis_client.py              # 新增（H3 修复 + Phase 4 low 修复）—— set_bitmap / get_bitmap / del_bitmap 抽象方法

tests/
├── test_parser_factory.py
├── test_splitter.py
├── test_knowledge_import.py
├── test_knowledge_unit_crud.py
└── test_knowledge_permission.py
```

---

## 2. Parser Factory

```python
# app/infrastructure/parsers/base_parser.py
"""解析器基类。"""

from abc import ABC, abstractmethod
from pathlib import Path


class BaseParser(ABC):
    @abstractmethod
    def parse(self, path: Path) -> str:
        """解析文件为纯文本。失败抛 ParseError。"""
        raise NotImplementedError


class ParseError(Exception):
    """解析失败的统一异常。"""

    def __init__(self, message: str, file_path: Path):
        super().__init__(message)
        self.file_path = file_path


# app/infrastructure/parsers/txt_parser.py
"""TXT 解析器：UTF-8 优先，失败回退 GBK。"""
from pathlib import Path


class TxtParser(BaseParser):
    def parse(self, path: Path) -> str:
        """UTF-8 → GBK 回退。

        步骤：
        1. 尝试 UTF-8 解码
        2. 失败则尝试 GBK
        3. 都失败抛 ParseError
        """
        raw = path.read_bytes()
        # 1. UTF-8
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            pass
        # 2. GBK
        try:
            return raw.decode("gbk")
        except UnicodeDecodeError as exc:
            raise ParseError(f"解码失败：{path.name}", path) from exc


# app/infrastructure/parsers/pdf_parser.py
"""PDF 解析：pypdf。"""
import pypdf
from pathlib import Path


class PDFParser(BaseParser):
    def parse(self, path: Path) -> str:
        """用 pypdf 抽所有页文本。

        步骤：
        1. PdfReader(path)
        2. 逐页 extract_text()
        3. 双换行拼接
        """
        try:
            reader = pypdf.PdfReader(str(path))
        except Exception as exc:
            raise ParseError(f"PDF 打开失败：{path.name}", path) from exc
        parts: list[str] = []
        for page in reader.pages:
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            if text:
                parts.append(text)
        return "\n\n".join(parts)


# app/infrastructure/parsers/docx_parser.py
"""Word 解析：python-docx。"""
from docx import Document
from pathlib import Path


class DocxParser(BaseParser):
    def parse(self, path: Path) -> str:
        """逐段提取 docx 段落文本。

        步骤：
        1. Document(path)
        2. 遍历 paragraphs
        3. 拼接（双换行）
        """
        try:
            doc = Document(str(path))
        except Exception as exc:
            raise ParseError(f"DOCX 打开失败：{path.name}", path) from exc
        parts = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(parts)


# app/infrastructure/parsers/markdown_parser.py
"""Markdown 解析：markdown-it 抽正文。"""
from markdown_it import MarkdownIt
from pathlib import Path


class MarkdownParser(BaseParser):
    def __init__(self):
        self._md = MarkdownIt()

    def parse(self, path: Path) -> str:
        """MarkdownIt 渲染后保留纯文本（演示期直接读源文本）。

        步骤：
        1. 读源文本
        2. 移除 HTML 标签（粗略）
        3. 保留代码块 / 表格 / 公式原样
        """
        raw = path.read_text(encoding="utf-8")
        # 移除 HTML 标签
        import re

        return re.sub(r"<[^>]+>", "", raw)


# app/infrastructure/parser_factory.py
"""Format-Handler-Map 路由。"""
from pathlib import Path

from app.infrastructure.parsers.base_parser import BaseParser, ParseError
from app.infrastructure.parsers.txt_parser import TxtParser
from app.infrastructure.parsers.pdf_parser import PDFParser
from app.infrastructure.parsers.docx_parser import DocxParser
from app.infrastructure.parsers.markdown_parser import MarkdownParser


class UnsupportedFormatError(Exception):
    pass


class ParserFactory:
    """按扩展名路由解析器。"""

    SUPPORTED_EXTENSIONS = {"pdf", "md", "docx", "txt"}

    def __init__(self):
        self._handlers: dict[str, BaseParser] = {
            "pdf": PDFParser(),
            "md": MarkdownParser(),
            "docx": DocxParser(),
            "txt": TxtParser(),
        }

    def parse(self, path: Path) -> str:
        """按 path.suffix 选解析器。

        步骤：
        1. 取 ext（去点、小写）
        2. 查 _handlers
        3. 调用 parser.parse(path)
        """
        ext = path.suffix.lstrip(".").lower()
        if ext not in self._handlers:
            raise UnsupportedFormatError(f"不支持的格式：{ext}")
        return self._handlers[ext].parse(path)


_parser_factory = ParserFactory()


def get_parser_factory() -> ParserFactory:
    """工厂单例（lifespan 启动时初始化）。"""
    return _parser_factory
```

---

## 2.4 EmbeddingService（C2 修复 — 基础设施层）

```python
# app/infrastructure/embedding.py
"""Embedding 客户端封装：text-embedding-3-small 调用。

使用 LangChain OpenAIEmbeddings 简化 SDK 调用；统一异步 embed / embed_batch 接口。
"""

from langchain_openai import OpenAIEmbeddings


class EmbeddingService:
    """OpenAI Embeddings 服务（text-embedding-3-small / dim=1536）。

    步骤：
    1. 构造时读取 settings.openai_api_key / openai_model
    2. async_embed_query：单文本 → 1536 维向量
    3. async_embed_documents：批量文本 → 列表向量
    """

    def __init__(self, model: str = "text-embedding-3-small", api_key: str | None = None):
        self._client = OpenAIEmbeddings(
            model=model,
            api_key=api_key,
            dimensions=1536,
        )

    async def embed(self, text: str) -> list[float]:
        """单文本嵌入。"""
        return await self._client.aembed_query(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量文本嵌入。"""
        return await self._client.aembed_documents(texts)
```

---

## 3. Splitter

> **关于 RedisClient**：本模块 §7 通过 `RedisClient.set_bitmap / get_bitmap / del_bitmap` 三个抽象方法访问鉴权位图，与 IMPL-M1 §2.4 `RedisClient` 对齐。RedisClient 需同时提供 `set / get / delete` 通用方法，供 §7 中 FAQ 缓存（faq:cache:<hash>，HSET + DEL）等非位图场景使用（low 修复）。

```python
# app/infrastructure/splitter.py
"""文本切片：保护块占位符 + RecursiveCharacterTextSplitter。"""

import re
import uuid
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter


@dataclass(slots=True)
class Chunk:
    text: str
    index: int  # 在原文档中的顺序


class Splitter:
    """保护块占位符切片法。

    流程：
    1. extract_protected_blocks：代码块/表格/公式 → UUID 占位符
    2. split_by_titles：按 ^#{1,6} 粗切
    3. refine_chunks：超长用 RecursiveCharacterTextSplitter 细切 + 短块合并
    4. 从后往前 replace 回原占位符内容
    """

    CHUNK_MAX_SIZE = 1000
    CHUNK_SIZE = 600
    CHUNK_OVERLAP = 100
    SEPARATORS = ["\n\n", "\n", "。", "！", "？"]

    # 保护块正则（按需扩展）
    PROTECTED_PATTERNS = [
        ("code_block", re.compile(r"```[\s\S]*?```", re.MULTILINE)),
        ("inline_code", re.compile(r"`[^`]+`")),
        ("table", re.compile(r"((?:\|[^\n]+\|\n)+)", re.MULTILINE)),
        ("formula_block", re.compile(r"\$\$[\s\S]*?\$\$", re.MULTILINE)),
        ("formula_inline", re.compile(r"\$[^$\n]+\$")),
    ]

    TITLE_PATTERN = re.compile(r"^#{1,6}\s+.+$", re.MULTILINE)

    def __init__(self):
        self._recursive = RecursiveCharacterTextSplitter(
            chunk_size=self.CHUNK_SIZE,
            chunk_overlap=self.CHUNK_OVERLAP,
            separators=self.SEPARATORS,
        )

    def split(self, text: str, title: str = "") -> list[Chunk]:
        """主入口：返回切片列表。"""
        # 1. 抽取保护块
        protected_map: dict[str, str] = {}
        masked = self._extract_protected_blocks(text, protected_map)

        # 2. 按标题粗切
        coarse_chunks = self._split_by_titles(masked, title=title)

        # 3. 细切 + 合并
        refined = self._refine_chunks(coarse_chunks)

        # 4. 还原占位符（从后往前避免错位）
        for chunk in refined:
            chunk.text = self._restore_placeholders(chunk.text, protected_map)

        return [Chunk(text=c.text, index=i) for i, c in enumerate(refined)]

    def _extract_protected_blocks(self, text: str, protected_map: dict[str, str]) -> str:
        """将保护块替换为 UUID 占位符。"""
        result = text
        for kind, pattern in self.PROTECTED_PATTERNS:
            for match in pattern.finditer(result):
                original = match.group(0)
                placeholder = f"⟦{kind}-{uuid.uuid4().hex[:8]}⟧"
                protected_map[placeholder] = original
                result = result.replace(original, placeholder, 1)
        return result

    def _split_by_titles(self, text: str, title: str) -> list[Chunk]:
        """按 Markdown 标题粗切。"""
        if not self.TITLE_PATTERN.search(text):
            # 无标题，整文一块
            return [Chunk(text=text, index=0)]
        # 粗切实现：按 \n 后跟 # 的位置切
        parts = self.TITLE_PATTERN.split(text)
        return [Chunk(text=p.strip(), index=i) for i, p in enumerate(parts) if p.strip()]

    def _refine_chunks(self, chunks: list[Chunk]) -> list[Chunk]:
        """超长细切 + 短块合并。"""
        refined: list[Chunk] = []
        buffer = ""
        for chunk in chunks:
            if len(chunk.text) <= self.CHUNK_SIZE:
                # 短块合并
                buffer += "\n\n" + chunk.text if buffer else chunk.text
                if len(buffer) >= self.CHUNK_SIZE:
                    refined.append(Chunk(text=buffer, index=0))
                    buffer = ""
            else:
                # 先 flush buffer
                if buffer:
                    refined.append(Chunk(text=buffer, index=0))
                    buffer = ""
                # 长块用 RecursiveCharacterTextSplitter 细切
                pieces = self._recursive.split_text(chunk.text)
                for p in pieces:
                    refined.append(Chunk(text=p, index=0))
        if buffer:
            refined.append(Chunk(text=buffer, index=0))
        return refined

    def _restore_placeholders(self, text: str, protected_map: dict[str, str]) -> str:
        """还原占位符为原内容。"""
        # 从后往前：避免占位符被其他规则识别
        for placeholder, original in sorted(protected_map.items(), reverse=True):
            text = text.replace(placeholder, original)
        return text
```

---

## 3.5 EmbeddingService

> **Embedding 服务**：OpenAI text-embedding-3-small（dim=1536）。使用 LangChain OpenAIEmbeddings 简化 SDK 调用；统一异步 embed / embed_batch 接口，供 §4 `_vectorize_and_update`、§6 `patch` / `create` 共用。

```python
# app/infrastructure/embedding.py
"""Embedding 服务：OpenAI text-embedding-3-small（dim=1536）。

使用 LangChain OpenAIEmbeddings 简化 SDK 调用；统一异步 embed / embed_batch 接口。
"""

from langchain_openai import OpenAIEmbeddings


class EmbeddingService:
    """OpenAI Embeddings 服务。

    步骤：
    1. 构造时读 settings.openai_api_key / settings.embedding_model
    2. embed：单文本 → 1536 维向量
    3. embed_batch：批量文本 → 列表向量
    """

    def __init__(self, model: str, api_key: str):
        self._client = OpenAIEmbeddings(
            model=model,
            api_key=api_key,
            dimensions=1536,
        )

    async def embed(self, text: str) -> list[float]:
        """单文本嵌入。"""
        return await self._client.aembed_query(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量文本嵌入。"""
        return await self._client.aembed_documents(texts)
```

---

## 4. KnowledgeImportService

```python
# app/services/knowledge_import_service.py
"""知识导入：单/批量文件解析 → 切片 → 入库 → 触发向量化。"""

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import BackgroundTasks

from app.config.settings import settings
from app.infrastructure.parser_factory import ParserFactory, UnsupportedFormatError, ParseError
from app.infrastructure.splitter import Splitter
from app.infrastructure.milvus_gateway import MilvusGateway
from app.infrastructure.file_storage import FileStorage
from app.infrastructure.embedding import EmbeddingService
from app.domain.user import CurrentUser


@dataclass(slots=True)
class ImportAccepted:
    file_name: str
    unit_codes: list[str]


@dataclass(slots=True)
class ImportRejected:
    file_name: str
    reason: str


class KnowledgeImportService:
    MAX_SINGLE_BYTES = 20 * 1024 * 1024  # 20MB
    MAX_TOTAL_BYTES = 200 * 1024 * 1024  # 200MB

    def __init__(
        self,
        unit_repo: KnowledgeUnitRepository,
        parser_factory: ParserFactory,
        splitter: Splitter,
        file_storage: FileStorage,
        milvus: MilvusGateway,
        embedding: EmbeddingService,  # C2 修复
    ):
        self._unit_repo = unit_repo
        self._parser = parser_factory
        self._splitter = splitter
        self._storage = file_storage
        self._milvus = milvus
        self._embedding = embedding

    async def import_files(
        self,
        files: list[UploadFile],
        user: CurrentUser,
        bg: BackgroundTasks,
    ) -> tuple[list[ImportAccepted], list[ImportRejected]]:
        """导入流程主入口。

        步骤：
        1. 校验：单文件 ≤ 20MB，总 ≤ 200MB
        2. 对每个文件：
           a. 落盘
           b. SHA-256 校验
           c. 解析
           d. 切片
           e. 批量 INSERT knowledge_units（status=vector_pending）
           f. add_task(milvus_upsert)
        3. 返回 accepted / rejected
        """
        # 1. 校验
        total_bytes = sum(f.size or 0 for f in files)
        if total_bytes > self.MAX_TOTAL_BYTES:
            raise FileSizeExceededError(detail=f"总大小 {total_bytes // 1024 // 1024}MB 超过 200MB")
        for f in files:
            if (f.size or 0) > self.MAX_SINGLE_BYTES:
                raise FileSizeExceededError(
                    detail=f"文件 {f.filename} 超过 20MB",
                )

        accepted: list[ImportAccepted] = []
        rejected: list[ImportRejected] = []

        for upload in files:
            try:
                # 2a. 落盘
                ext = Path(upload.filename).suffix.lstrip(".").lower()
                if ext not in ParserFactory.SUPPORTED_EXTENSIONS:
                    rejected.append(
                        ImportRejected(
                            file_name=upload.filename,
                            reason="unsupported_format",
                        )
                    )
                    continue
                saved_path = await self._storage.save(upload, ext=ext)

                # 2b. SHA-256 校验
                content_hash = await self._storage.compute_sha256(saved_path)
                existing = await self._unit_repo.find_by_content_hash(content_hash)
                if existing is not None:
                    rejected.append(
                        ImportRejected(
                            file_name=upload.filename,
                            reason="duplicate_content",
                        )
                    )
                    # 删除已落盘（拒绝重复）
                    saved_path.unlink(missing_ok=True)
                    continue

                # 2c. 解析
                try:
                    raw_text = self._parser.parse(saved_path)
                except (ParseError, UnsupportedFormatError) as exc:
                    logger.warning(
                        "knowledge.parse.fail filename={} error={}", upload.filename, exc
                    )
                    rejected.append(
                        ImportRejected(
                            file_name=upload.filename,
                            reason="parse_failed",
                        )
                    )
                    continue

                # 2d. 切片
                title = Path(upload.filename).stem
                chunks = self._splitter.split(raw_text, title=title)

                # 2e. 批量 INSERT
                unit_codes = [self._generate_unit_code(i) for i in range(len(chunks))]
                unit_records = [
                    KnowledgeUnitRecord(
                        unit_code=code,
                        title=f"{title} #{i + 1}",
                        content=chunk.text,
                        summary=chunk.text[:200],
                        source_file_name=upload.filename,
                        file_type=ext,
                        file_size=upload.size,
                        content_hash=content_hash,
                        status="vector_pending",
                        creator_id=user.id,
                    )
                    for i, (code, chunk) in enumerate(zip(unit_codes, chunks))
                ]
                inserted_ids = await self._unit_repo.batch_insert(unit_records)

                # 2f. 触发向量化（背景任务）
                bg.add_task(
                    self._vectorize_and_update,
                    unit_ids=inserted_ids,
                    chunks=chunks,
                )

                accepted.append(
                    ImportAccepted(
                        file_name=upload.filename,
                        unit_codes=unit_codes,
                    )
                )
                logger.info("knowledge.import file={} units={}", upload.filename, len(unit_codes))

            except Exception as exc:
                logger.error("knowledge.import.fail file={} error={}", upload.filename, exc)
                rejected.append(
                    ImportRejected(
                        file_name=upload.filename,
                        reason="internal_error",
                    )
                )

        return accepted, rejected

    async def _vectorize_and_update(self, unit_ids: list[int], chunks: list[Chunk]) -> None:
        """背景任务：embed → milvus upsert → 更新 status。

        步骤：
        1. 批量调 embedding_service.embed
        2. milvus.upsert
        3. UPDATE knowledge_units SET status='active'
        """
        try:
            # 1. 批量 embed
            embeddings = await self._embedding.embed_batch([c.text for c in chunks])
            # 2. milvus upsert
            await self._milvus.upsert(
                ids=unit_ids,
                texts=[c.text for c in chunks],
                embeddings=embeddings,
            )
            # 3. 更新 status
            await self._unit_repo.update_status_batch(unit_ids, "active")
            logger.info("knowledge.vectorize.success unit_ids={}", unit_ids)
        except Exception as exc:
            logger.warning(
                "knowledge.vectorize.fail unit_ids={} error={}",
                unit_ids,
                exc,
            )
            # 失败时保持 status='vector_pending'，后台重试

    def _generate_unit_code(self, index: int) -> str:
        """生成业务编号：KU-YYYYMM-NNNNNN。"""
        from datetime import datetime

        ym = datetime.now().strftime("%Y%m")
        # 演示期简化：用 uuid 后 6 位
        return f"KU-{ym}-{uuid.uuid4().hex[:6].upper()}"
```

```python
# app/infrastructure/file_storage.py
"""本地文件存储。"""

import hashlib
import shutil
from pathlib import Path


class FileStorage:
    def __init__(self, base_dir: str):
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    async def save(self, upload, *, ext: str) -> Path:
        """保存上传文件到 base_dir/{uuid}.{ext}。"""
        file_id = uuid.uuid4().hex
        target = self._base / f"{file_id}.{ext}"
        with target.open("wb") as f:
            shutil.copyfileobj(upload.file, f)
        return target

    async def compute_sha256(self, path: Path) -> str:
        """计算 SHA-256（hex 字符串）。"""
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
```

---

## 5. KnowledgeUnitRepository / UnitPermissionRepository

```python
# app/repositories/knowledge_unit_repository.py
"""知识单元 ORM 仓储：knowledge_units 表 + unit_permissions 关联表。"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import (
    KnowledgeUnitRecord,
    UnitPermissionRecord,
    DepartmentRecord,
    RoleRecord,
    UserRecord,
)


class KnowledgeUnitRepository:
    """CRUD + 数据权限查询封装。"""

    def __init__(self, session: AsyncSession):
        self._session = session

    # ----- 单元 CRUD -----
    async def find_by_id(self, unit_id: int) -> KnowledgeUnitRecord | None: ...
    async def find_by_content_hash(self, content_hash: str) -> KnowledgeUnitRecord | None: ...
    async def insert(self, record: KnowledgeUnitRecord) -> None: ...
    async def update(self, record: KnowledgeUnitRecord) -> None: ...
    async def batch_insert(self, records: list[KnowledgeUnitRecord]) -> list[int]: ...
    async def batch_delete(self, ids: list[int]) -> int: ...
    async def list_paginated(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str | None,
        category: str | None,
        status: str | None,
    ) -> tuple[list[KnowledgeUnitRecord], int]: ...
    async def update_status_batch(self, ids: list[int], status: str) -> None: ...

    # ----- 单字段查询（M6 FAQ 缓存版本校验 + M4 组装） -----
    async def get_updated_at(self, unit_id: int) -> datetime | None:
        """返回 knowledge_units.updated_at（FAQ 缓存版本校验用）。"""
        stmt = select(KnowledgeUnitRecord.updated_at).where(KnowledgeUnitRecord.id == unit_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_status(self, unit_id: int) -> str | None:
        """返回 knowledge_units.status。"""
        stmt = select(KnowledgeUnitRecord.status).where(KnowledgeUnitRecord.id == unit_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_title(self, unit_id: int) -> str | None:
        """返回 knowledge_units.title。"""
        stmt = select(KnowledgeUnitRecord.title).where(KnowledgeUnitRecord.id == unit_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    # ----- 批量查询（M4 assemble_prompt / permission_filter） -----
    async def list_content_for_ids(self, unit_ids: list[int]) -> list[KnowledgeUnitRecord]:
        """M4 assemble_prompt 用：批量取 unit_id → 完整记录（含 content）。"""
        if not unit_ids:
            return []
        stmt = select(KnowledgeUnitRecord).where(KnowledgeUnitRecord.id.in_(unit_ids))
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_permissions_for_units(self, unit_ids: list[int]) -> list[UnitPermissionRecord]:
        """M4 permission_filter 用：批量取 unit_id → UnitPermissionRecord。"""
        if not unit_ids:
            return []
        stmt = select(UnitPermissionRecord).where(UnitPermissionRecord.unit_id.in_(unit_ids))
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_permissions_for_unit(self, unit_id: int) -> list[UnitPermissionRecord]: ...
    async def replace_permissions(
        self, unit_id: int, perms: list[UnitPermissionRequest]
    ) -> None: ...

    # ----- 鉴权位图用：4 路 UNION 查询 -----
    async def list_units_by_target_type(self, target_type: str) -> list[int]: ...
    async def list_user_dept_ids_with_ancestors(self, dept_id: int | None) -> list[int]: ...
    async def list_units_by_target_type_and_ids(
        self, target_type: str, target_ids: list[int]
    ) -> list[int]: ...
    async def load_current_user(self, user_id: int) -> CurrentUser | None: ...
    async def list_permissions_summary_for_units(self, unit_ids: list[int]) -> dict[int, str]: ...

    # ----- target 校验用 -----
    async def find_department(self, dept_id: int) -> DepartmentRecord | None: ...
    async def find_role(self, role_id: int) -> RoleRecord | None: ...
    async def find_user(self, user_id: int) -> UserRecord | None: ...


# app/repositories/unit_permission_repository.py
"""unit_permissions / faqs 表混合仓储（M6 FaqCacheService 用）。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import UnitPermissionRecord, FaqRecord


class UnitPermissionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def find_for_unit(self, unit_id: int) -> list[UnitPermissionRecord]: ...
    async def replace(self, unit_id: int, perms: list) -> None: ...

    async def list_faqs_by_related_unit_ids(self, unit_ids: list[int]) -> list[FaqRecord]:
        """M6 FaqCacheService.invalidate_by_unit_ids 用。

        步骤：
        1. SELECT FROM faqs WHERE related_unit_id IN (?)
        2. 返回所有挂载到这些 unit_id 的 FAQ 记录
        """
        if not unit_ids:
            return []
        stmt = select(FaqRecord).where(FaqRecord.related_unit_id.in_(unit_ids))
        return list((await self._session.execute(stmt)).scalars().all())
```

---

## 6. KnowledgeUnitService

```python
# app/services/knowledge_unit_service.py
class KnowledgeUnitService:
    def __init__(
        self,
        repo: KnowledgeUnitRepository,
        milvus: MilvusGateway,
        redis: RedisClient,
        faq_cache: FaqCacheService,  # C1 修复：缺注入，batch_delete 时失效 FAQ 缓存
        embedding: EmbeddingService,  # C2 修复
    ):
        self._repo = repo
        self._milvus = milvus
        self._redis = redis
        self._faq_cache = faq_cache
        self._embedding = embedding

    async def list(self, *, page, page_size, keyword, category, status, user) -> UnitListResponse:
        """列表查询。

        步骤：
        1. 调 repo.list_paginated
        2. 批量 enrich：permissions_summary（"全局公开" / "研发部+管理员"）
        """
        rows, total = await self._repo.list_paginated(
            page=page,
            page_size=page_size,
            keyword=keyword,
            category=category,
            status=status,
        )
        # enrich permissions_summary
        unit_ids = [r.id for r in rows]
        perm_map = await self._repo.list_permissions_summary_for_units(unit_ids)
        items = [
            KnowledgeUnitResponse(
                id=r.id,
                unit_code=r.unit_code,
                title=r.title,
                summary=r.summary,
                category=r.category,
                file_type=r.file_type,
                source_file_name=r.source_file_name,
                permissions_summary=perm_map.get(r.id, "未配置"),
                creator_id=r.creator_id,
                creator_name=r.creator.display_name if r.creator else "",
                status=r.status,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in rows
        ]
        return UnitListResponse(items=items, page=page, page_size=page_size, total=total)

    async def get(self, unit_id: int, user: CurrentUser) -> KnowledgeUnitDetailResponse:
        """详情：含 content + permissions 列表。"""
        # 1. 查 unit
        record = await self._repo.find_by_id(unit_id)
        if record is None:
            raise KnowledgeUnitNotFoundError(unit_id)

        # 2. 查权限
        permissions = await self._repo.list_permissions_for_unit(unit_id)

        # 3. 转为 DTO（含 target_label）
        perm_entries = [
            PermissionEntryResponse(
                target_type=p.target_type,
                target_id=p.target_id,
                target_label=await self._resolve_target_label(p),
            )
            for p in permissions
        ]

        return KnowledgeUnitDetailResponse(
            id=record.id,
            unit_code=record.unit_code,
            title=record.title,
            content=record.content,
            summary=record.summary,
            category=record.category,
            file_type=record.file_type,
            source_file_name=record.source_file_name,
            permissions=perm_entries,
            creator_id=record.creator_id,
            creator_name=record.creator.display_name if record.creator else "",
            status=record.status,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    async def patch(
        self, unit_id: int, data: KnowledgeUnitPatch, user: CurrentUser
    ) -> KnowledgeUnitResponse:
        """部分更新。

        步骤：
        1. 校验存在
        2. 校验 title / content 非空
        3. UPDATE
        4. 内容变更 → 重算 content_hash → milvus_upsert
        5. 同步更新 unit_updated_at（影响 FAQ 缓存）
        """
        record = await self._repo.find_by_id(unit_id)
        if record is None:
            raise KnowledgeUnitNotFoundError(unit_id)

        content_changed = False
        if data.title is not None:
            if not data.title.strip():
                raise ValidationError("title_empty")
            record.title = data.title
        if data.content is not None:
            if not data.content.strip():
                raise ValidationError("content_empty")
            record.content = data.content
            # 重算 hash
            record.content_hash = hashlib.sha256(data.content.encode()).hexdigest()
            content_changed = True
        if data.summary is not None:
            record.summary = data.summary
        if data.category is not None:
            record.category = data.category
        await self._session.flush()

        # 内容变更触发向量重算
        if content_changed:
            await self._milvus.upsert(
                ids=[record.id],
                texts=[record.content],
                embeddings=[await self._embedding.embed(record.content)],
            )

        logger.info("knowledge.unit.patch unit_id={} actor={}", unit_id, user.id)
        return await self._to_response(record)

    async def batch_delete(self, ids: list[int], user: CurrentUser) -> int:
        """批量删除（含 Milvus 向量清理）。

        步骤：
        1. 校验数量上限 200
        2. DELETE FROM knowledge_units WHERE id IN (?)
        3. CASCADE 自动清理 unit_permissions
        4. milvus.delete(ids)
        5. 失效 FAQ 缓存（unit_updated_at 已变）
        """
        if len(ids) > 200:
            raise ValidationError("batch_size_exceeded")
        if len(ids) == 0:
            return 0
        # 1. DB 删除
        deleted_count = await self._repo.batch_delete(ids)
        # 2. Milvus 向量删除
        await self._milvus.delete(ids)
        # 3. 失效相关 FAQ 缓存（任何挂载 unit_id 的 FAQ）
        await self._faq_cache.invalidate_by_unit_ids(ids)
        logger.info(
            "knowledge.unit.batch_delete actor={} ids={} count={}", user.id, ids, deleted_count
        )
        return deleted_count

    async def create(
        self,
        data: KnowledgeUnitCreate,
        user: CurrentUser,
    ) -> KnowledgeUnitResponse:
        """手动新建单元 + 一键建档调用入口。

        步骤：
        1. 校验 content 非空
        2. 计算 content_hash = SHA-256(data.content)
        3. content_hash 幂等检查
        4. INSERT knowledge_units（status=active，手动创建不等向量化）
        5. 触发 milvus_upsert（演示期同步）
        6. 缺口回填：若 data.prefill_from_gap_id 非空，标记 gap 已解决
        7. 返回 KnowledgeUnitResponse
        """
        # 1. 校验 content 非空
        if not data.content or not data.content.strip():
            raise ValidationError("content_empty")

        content_hash = __import__("hashlib").sha256(data.content.encode("utf-8")).hexdigest()

        # 2. 幂等检查
        existing = await self._repo.find_by_content_hash(content_hash)
        if existing is not None:
            raise DuplicateContentError()

        # 3. INSERT
        unit_code = self._generate_unit_code()
        record = KnowledgeUnitRecord(
            unit_code=unit_code,
            title=data.title,
            content=data.content,
            summary=data.summary or data.content[:200],
            category=data.category,
            source_file_name=data.source_file_name,
            file_type=None,
            file_size=None,
            content_hash=content_hash,
            status="active",  # 手动创建默认 active（不等向量化）
            creator_id=user.id,
        )
        await self._repo.insert(record)

        # 4. 触发向量化（演示期同步；后续可切 BackgroundTask）
        await self._milvus.upsert(
            ids=[record.id],
            texts=[record.content],
            embeddings=[await self._embedding.embed(record.content)],
        )

        # 5. 缺口回填
        if data.prefill_from_gap_id is not None:
            await self._gap_repo.mark_resolved(data.prefill_from_gap_id, unit_id=record.id)

        # 6. 日志
        __import__("loguru").logger.info(
            "knowledge.unit.create unit_id={} actor={}", record.id, user.id
        )
        return await self._to_response(record)

    def _generate_unit_code(self) -> str:
        """生成业务编号：KU-YYYYMM-NNNNNN。"""
        from datetime import datetime

        ym = datetime.now().strftime("%Y%m")
        return f"KU-{ym}-{uuid.uuid4().hex[:6].upper()}"
```

---

## 7. KnowledgePermissionService（核心）

```python
# app/services/knowledge_permission_service.py
"""数据权限服务：鉴权算法 + check-permissions 共享接口。"""

from app.domain.user import CurrentUser


class KnowledgePermissionService:
    def __init__(self, unit_repo: KnowledgeUnitRepository, redis: RedisClient):
        self._repo = unit_repo
        self._redis = redis

    async def configure(
        self, unit_id: int, req: ConfigurePermissionsRequest, user: CurrentUser
    ) -> list[PermissionEntryResponse]:
        """全量替换知识单元的数据权限。

        步骤：
        1. 校验知识单元存在
        2. 校验每条 target 存在（部门 / 角色 / 用户）
        3. 至少一条权限
        4. 限制：每个 unit 最多一条 global
        5. DELETE + INSERT（同一事务）
        6. 返回新权限列表
        """
        # 1. 存在
        unit = await self._repo.find_by_id(unit_id)
        if unit is None:
            raise KnowledgeUnitNotFoundError(unit_id)

        # 2-3. 校验
        if not req.permissions:
            raise InvalidPermissionConfigurationError("empty_permissions")

        global_count = sum(1 for p in req.permissions if p.target_type == "global")
        if global_count > 1:
            raise InvalidPermissionConfigurationError("multiple_global")

        # 4. 校验 target 存在
        for p in req.permissions:
            await self._validate_target(p)

        # 5. 替换
        await self._repo.replace_permissions(unit_id, req.permissions)

        # 6. 返回
        logger.info(
            "unit.permission_config unit_id={} actor={} counts={}",
            unit_id,
            user.id,
            len(req.permissions),
        )
        return await self._build_response(unit_id)

    async def _validate_target(self, p: PermissionEntryRequest) -> None:
        """校验 target 实体存在。"""
        if p.target_type == "global":
            return
        if p.target_id is None:
            raise InvalidPermissionConfigurationError("target_id_required")
        if p.target_type == "department":
            dept = await self._repo.find_department(p.target_id)
            if dept is None:
                raise InvalidPermissionConfigurationError(f"department_not_found: {p.target_id}")
        elif p.target_type == "role":
            role = await self._repo.find_role(p.target_id)
            if role is None:
                raise InvalidPermissionConfigurationError(f"role_not_found: {p.target_id}")
        elif p.target_type == "user":
            user = await self._repo.find_user(p.target_id)
            if user is None:
                raise InvalidPermissionConfigurationError(f"user_not_found: {p.target_id}")

    async def load_user_permission_bitmap(self, user: CurrentUser) -> set[int]:
        """加载用户的可访问 unit 集合（全集，缓存 Redis）。

        步骤：
        1. 查 Redis 鉴权位图（key: auth:bitmap:{user_id}）—— 通过 RedisClient.set_bitmap / get_bitmap / del_bitmap 抽象方法
        2. 缺失则重算：4 路 UNION 查询
        3. 写 Redis TTL 5 分钟（set_bitmap）
        4. 返回 set[int]
        """
        # 1. 读 Redis
        cached = await self._redis.get_bitmap(user.id)
        if cached is not None:
            return set(int(x) for x in cached)

        # 2. 重算
        # 2.1 global
        global_ids = await self._repo.list_units_by_target_type("global")
        # 2.2 department（含祖先链）
        dept_ids = await self._repo.list_user_dept_ids_with_ancestors(user.department_id)
        dept_units = await self._repo.list_units_by_target_type_and_ids("department", dept_ids)
        # 2.3 role
        role_ids = user.role_ids
        role_units = await self._repo.list_units_by_target_type_and_ids("role", role_ids)
        # 2.4 user
        user_units = await self._repo.list_units_by_target_type_and_ids("user", [user.id])

        # 合并
        bitmap = set(global_ids) | set(dept_units) | set(role_units) | set(user_units)

        # 3. 写 Redis
        await self._redis.set_bitmap(
            user_id=user.id,
            permissions=list(bitmap),
            ttl=settings.auth_bitmap_ttl_seconds,
        )

        return bitmap

    async def check_permissions(
        self, user_id: int, unit_ids: list[int]
    ) -> CheckPermissionsResponse:
        """M3 共享接口：拆分为 authorized / unauthorized。

        步骤：
        1. 加载用户 CurrentUser
        2. 加载用户位图
        3. 拆分 unit_ids
        """
        # 1. 查用户
        current = await self._repo.load_current_user(user_id)
        if current is None:
            raise UserNotFoundError(user_id)

        # 2. 位图
        bitmap = await self.load_user_permission_bitmap(current)

        # 3. 拆分
        authorized = [uid for uid in unit_ids if uid in bitmap]
        unauthorized = [uid for uid in unit_ids if uid not in bitmap]

        return CheckPermissionsResponse(
            authorized_unit_ids=authorized,
            unauthorized_unit_ids=unauthorized,
        )

    def compute_user_permission_bitmap_sync(
        self,
        user,  # SimpleNamespace 或 CurrentUser
        unit_permissions: list[UnitPermissionRecord],
    ) -> set[int]:
        """纯函数式内存 OR 运算（保留 self 是为 LangGraph 注入一致性）。

        步骤：
        1. 按 unit_id 聚合 permissions
        2. 对每个 unit 检查：global / dept / role / user 任意一项匹配
        3. 返回满足条件的 unit_id set
        """
        # 1. 聚合：unit_id → [permissions]
        per_unit: dict[int, list[UnitPermissionRecord]] = {}
        for p in unit_permissions:
            per_unit.setdefault(p.unit_id, []).append(p)

        # 2. 检查每个 unit
        authorized: set[int] = set()
        for uid, perms in per_unit.items():
            for p in perms:
                if p.target_type == "global":
                    authorized.add(uid)
                    break
                if p.target_type == "department" and p.target_id in user.dept_ids:
                    authorized.add(uid)
                    break
                if p.target_type == "role" and p.target_id in user.role_ids:
                    authorized.add(uid)
                    break
                if p.target_type == "user" and p.target_id == user.id:
                    authorized.add(uid)
                    break
        return authorized

    async def invalidate_user_bitmap(self, user_id: int) -> None:
        """权限变更后主动失效（供 M2 角色权限变更调用）。"""
        await self._redis.del_bitmap(user_id)
```

---

## 8. Router

```python
# app/api/routers/knowledge_router.py
router = APIRouter(prefix="/api/v1", tags=["knowledge"])


@router.post(
    "/knowledge/import",
    response_model=ImportTaskResponse,
    dependencies=[Depends(require_permission("knowledge:write"))],
)
async def import_knowledge(
    bg: BackgroundTasks,
    user: CurrentUserDep,
    service: KnowledgeImportServiceDep,
    files: list[UploadFile] = File(...),
):
    """批量上传（multipart，最多 200MB）。"""
    if len(files) > 50:
        raise ValidationError("too_many_files")
    accepted, rejected = await service.import_files(files, user, bg)
    return ImportTaskResponse(
        task_id=uuid.uuid4().hex,
        accepted_count=len(accepted),
        rejected=rejected,
    )


@router.get(
    "/knowledge-units",
    response_model=UnitListResponse,
    dependencies=[Depends(require_permission("knowledge:read"))],
)
async def list_units(
    service: KnowledgeUnitServiceDep,
    user: CurrentUserDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = None,
    category: str | None = None,
    status: str | None = None,
):
    return await service.list(
        page=page,
        page_size=page_size,
        keyword=keyword,
        category=category,
        status=status,
        user=user,
    )


@router.get(
    "/knowledge-units/{unit_id}",
    response_model=KnowledgeUnitDetailResponse,
    dependencies=[Depends(require_permission("knowledge:read"))],
)
async def get_unit(unit_id: int, service: KnowledgeUnitServiceDep, user: CurrentUserDep):
    return await service.get(unit_id, user)


@router.patch(
    "/knowledge-units/{unit_id}",
    response_model=KnowledgeUnitResponse,
    dependencies=[Depends(require_permission("knowledge:write"))],
)
async def patch_unit(
    unit_id: int, data: KnowledgeUnitPatch, service: KnowledgeUnitServiceDep, user: CurrentUserDep
):
    return await service.patch(unit_id, data, user)


@router.delete(
    "/knowledge-units",
    status_code=204,
    dependencies=[Depends(require_permission("knowledge:delete"))],
)
async def batch_delete_units(
    req: BatchDeleteRequest, service: KnowledgeUnitServiceDep, user: CurrentUserDep
):
    await service.batch_delete(req.ids, user)


@router.post(
    "/knowledge-units/{unit_id}/permissions",
    response_model=list[PermissionEntryResponse],
    dependencies=[Depends(require_permission("knowledge:assign_permission"))],
)
async def configure_permissions(
    unit_id: int,
    req: ConfigurePermissionsRequest,
    service: KnowledgePermissionServiceDep,
    user: CurrentUserDep,
):
    """配置知识单元数据权限（四维：global / department / role / user）。

    鉴权：`knowledge:assign_permission` 权限码（仅知识管理员；普通编辑者无权限，H5 修复）。
    替换语义：DELETE + INSERT 同一事务，至少一条权限，global 行全局唯一。
    """
    return await service.configure(unit_id, req, user)


@router.post(
    "/knowledge/check-permissions",
    response_model=CheckPermissionsResponse,
    dependencies=[Depends(require_permission("knowledge:check"))],
)
async def check_permissions(
    req: CheckPermissionsRequest,
    service: KnowledgePermissionServiceDep,
    user: CurrentUserDep,
):
    """**共享接口**：M4 AI 对话内部调用，前端亦可直接调用。

    鉴权：knowledge:check 权限码（防普通用户越权探测他人权限分布，H1 修复）。
    """
    return await service.check_permissions(req.user_id, req.unit_ids)
```

---

## 8.5 关键 Pydantic Schema

```python
# app/api/schemas/knowledge_unit_schema.py
"""知识单元 CRUD / 权限配置 Request/Response 模型。"""

from pydantic import BaseModel, Field


class KnowledgeUnitCreate(BaseModel):
    """手动新建单元请求体（被 M6 一键建档复用）。"""

    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    summary: str | None = Field(default=None, max_length=512)
    category: str | None = Field(default=None, max_length=64)
    source_file_name: str | None = Field(default=None, max_length=255)
    # M6 一键建档可填：缺口 id 触发回填
    prefill_from_gap_id: int | None = None


class KnowledgeUnitPatch(BaseModel):
    """PATCH /api/v1/knowledge-units/{unit_id} 部分更新请求体。"""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, min_length=1)
    summary: str | None = Field(default=None, max_length=512)
    category: str | None = Field(default=None, max_length=64)


class KnowledgeUnitResponse(BaseModel):
    """单元列表/详情通用响应。"""

    id: int
    unit_code: str
    title: str
    summary: str | None
    category: str | None
    file_type: str | None
    source_file_name: str | None
    permissions_summary: str
    creator_id: int
    creator_name: str
    status: str
    created_at: str
    updated_at: str


class KnowledgeUnitDetailResponse(KnowledgeUnitResponse):
    """详情：附加 content + permissions 列表。"""

    content: str
    permissions: list["PermissionEntryResponse"]


class PermissionEntryRequest(BaseModel):
    target_type: str = Field(pattern="^(global|department|role|user)$")
    target_id: int | None = None


class ConfigurePermissionsRequest(BaseModel):
    permissions: list[PermissionEntryRequest] = Field(min_length=1)


class PermissionEntryResponse(BaseModel):
    target_type: str
    target_id: int | None
    target_label: str | None


class CheckPermissionsRequest(BaseModel):
    user_id: int
    unit_ids: list[int]


class CheckPermissionsResponse(BaseModel):
    authorized_unit_ids: list[int]
    unauthorized_unit_ids: list[int]
```

---

## 9. 测试用例

```python
# tests/test_parser_factory.py
@pytest.mark.asyncio
class TestParserFactory:
    async def test_pdf_parser_extracts_text(self, parser_factory, tmp_path):
        # 构造简单 PDF（用 reportlab 跳过，直接放 fixture）
        pdf = tmp_path / "sample.pdf"
        pdf.write_bytes(SAMPLE_PDF_BYTES)
        text = parser_factory.parse(pdf)
        assert "Hello" in text  # 来自 fixture 的内容

    async def test_txt_parser_utf8_fallback_gbk(self, parser_factory, tmp_path):
        txt = tmp_path / "win.txt"
        txt.write_bytes("你好世界".encode("gbk"))  # GBK 编码
        text = parser_factory.parse(txt)
        assert text == "你好世界"

    async def test_unsupported_format_raises(self, parser_factory, tmp_path):
        xlsx = tmp_path / "x.xlsx"
        xlsx.write_bytes(b"fake")
        with pytest.raises(UnsupportedFormatError):
            parser_factory.parse(xlsx)


# tests/test_splitter.py
@pytest.mark.asyncio
class TestSplitter:
    async def test_short_text_single_chunk(self, splitter):
        text = "短文本不超过 600 字" * 10
        chunks = splitter.split(text, title="t")
        assert len(chunks) == 1

    async def test_long_text_multiple_chunks(self, splitter):
        text = "段落。\n\n" * 500  # 约 4000 字
        chunks = splitter.split(text, title="t")
        assert len(chunks) > 1
        # 检查重叠窗口
        for i, chunk in enumerate(chunks[1:], 1):
            assert len(chunk.text) <= splitter.CHUNK_MAX_SIZE

    async def test_code_blocks_not_split(self, splitter):
        # 长代码块应被保护
        code = "```python\n" + "x = 1\n" * 1000 + "```"
        chunks = splitter.split(code, title="t")
        # 代码块应完整保留在某一片
        combined = "\n".join(c.text for c in chunks)
        assert "```python" in combined
        assert "```" in combined


# tests/test_knowledge_import.py
@pytest.mark.asyncio
class TestImport:
    async def test_import_pdf_creates_units(self, async_client, admin_token, seeded_import):
        files = [("files", ("test.pdf", SAMPLE_PDF_BYTES, "application/pdf"))]
        resp = await async_client.post(
            "/api/v1/knowledge/import",
            files=files,
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["accepted_count"] == 1

    async def test_duplicate_content_rejected(self, async_client, admin_token, seeded_content):
        # 二次导入同文件
        ...
        resp = await async_client.post(
            "/api/v1/knowledge/import",
            files=[("files", ("dup.pdf", SAME_BYTES, "application/pdf"))],
            headers=auth_header(admin_token),
        )
        body = resp.json()
        assert body["accepted_count"] == 0
        assert body["rejected"][0]["reason"] == "duplicate_content"

    async def test_file_size_exceeded_returns_413(self, async_client, admin_token):
        big = b"x" * (21 * 1024 * 1024)
        files = [("files", ("big.txt", big, "text/plain"))]
        resp = await async_client.post(
            "/api/v1/knowledge/import",
            files=files,
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 413


# tests/test_knowledge_permission.py
@pytest.mark.asyncio
class TestPermission:
    async def test_configure_global_permission(self, async_client, admin_token, seeded_unit):
        resp = await async_client.post(
            "/api/v1/knowledge-units/1/permissions",
            json={"permissions": [{"target_type": "global", "target_id": None}]},
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200

    async def test_configure_multiple_global_returns_422(self, async_client, admin_token):
        resp = await async_client.post(
            "/api/v1/knowledge-units/1/permissions",
            json={
                "permissions": [
                    {"target_type": "global", "target_id": None},
                    {"target_type": "global", "target_id": None},
                ]
            },
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 422

    async def test_check_permissions_splits_authorized_unauthorized(
        self, async_client, admin_token, seeded_units_with_mixed_perms
    ):
        req = {"user_id": 3, "unit_ids": [1, 2, 3, 4]}
        resp = await async_client.post(
            "/api/v1/knowledge/check-permissions",
            json=req,
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert set(body["authorized_unit_ids"]) | set(body["unauthorized_unit_ids"]) == {1, 2, 3, 4}
        assert set(body["authorized_unit_ids"]) & set(body["unauthorized_unit_ids"]) == set()

    async def test_check_permissions_requires_perm(
        self,
        async_client,
        regular_user_token,
    ):
        """普通用户（无 knowledge:check）调用 check-permissions 返回 403 permission_denied。"""
        req = {"user_id": 1, "unit_ids": [1, 2]}
        resp = await async_client.post(
            "/api/v1/knowledge/check-permissions",
            json=req,
            headers=auth_header(regular_user_token),
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission_denied"

    def test_compute_user_bitmap_or_logic(self):
        # 纯函数单测
        user = CurrentUser(
            id=1,
            dept_ids=[1, 2],
            role_ids=[3],  # 简化字段
        )
        # 构造 UnitPermissionRecord 列表（4 类）
        perms = [
            UnitPermissionRecord(unit_id=10, target_type="global", target_id=None),
            UnitPermissionRecord(unit_id=11, target_type="department", target_id=2),  # 命中
            UnitPermissionRecord(unit_id=12, target_type="role", target_id=3),  # 命中
            UnitPermissionRecord(unit_id=13, target_type="user", target_id=1),  # 命中
            UnitPermissionRecord(unit_id=14, target_type="department", target_id=99),  # 不命中
        ]
        svc = KnowledgePermissionService(unit_repo=None, redis=None)  # 纯函数只需占位
        bitmap = svc.compute_user_permission_bitmap_sync(user, perms)
        assert bitmap == {10, 11, 12, 13}  # 14 不命中
```

---

## 10. 验收 Checklist

- [ ] 4 格式 PDF/MD/DOCX/TXT 都能解析
- [ ] UTF-8 TXT 失败回退 GBK 正常
- [ ] 代码块/表格被占位符保护，不被切碎
- [ ] SHA-256 重复内容拒绝导入
- [ ] 单文件 20MB / 总 200MB 限制
- [ ] 数据权限 4 类配置 + OR 逻辑生效
- [ ] check-permissions 拆分正确
- [ ] 单元删除同步清理 Milvus 向量
- [ ] 内容更新触发 Milvus 重算 + FAQ 缓存失效