"""SQLAlchemy 2.0 async engine + 11 张表 ORM + AsyncSessionLocal + Depends。

> 11 表定义与 docs/数据对象文档.md 字段一一对应。
> - 主键 BIGINT UNSIGNED AUTO_INCREMENT（SQLAlchemy BigInteger + 自增）
> - 创建/更新时间 server_default=now() + onupdate=now()
> - 软删除：仅业务 status 字段（users.status / faqs.status /
>                knowledge_gaps.status）
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime

from fastapi import Depends
from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config.settings import settings


class BaseORM(DeclarativeBase):
    """所有 ORM 模型的基类。"""


# ════════════════════════════════════════════════════════════
# 组织权限域（5 张）
# ════════════════════════════════════════════════════════════


class UserRecord(BaseORM):
    """users 表 —— 系统登录主体。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    department_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("departments.id"), nullable=False
    )
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (Index("idx_department", "department_id"),)


class DepartmentRecord(BaseORM):
    """departments 表 —— 树形组织节点。"""

    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("departments.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    leader_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("idx_parent", "parent_id"),
        Index("idx_leader", "leader_id"),
    )


class RoleRecord(BaseORM):
    """roles 表 —— 内置 + 自定义角色。"""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role_name: Mapped[str] = mapped_column(String(64), nullable=False)
    role_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class UserRoleRecord(BaseORM):
    """user_roles 表 —— 用户-角色多对多。"""

    __tablename__ = "user_roles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uk_user_role"),
        Index("idx_role", "role_id"),
    )


class RolePermissionRecord(BaseORM):
    """role_permissions 表 —— 角色-权限码多对多。"""

    __tablename__ = "role_permissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    permission_code: Mapped[str] = mapped_column(String(64), nullable=False)
    permission_type: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("role_id", "permission_code", name="uk_role_perm"),
        Index("idx_code", "permission_code"),
    )


# ════════════════════════════════════════════════════════════
# 知识资产域（2 张）
# ════════════════════════════════════════════════════════════


class KnowledgeUnitRecord(BaseORM):
    """knowledge_units 表 —— 知识切片单元。"""

    __tablename__ = "knowledge_units"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    unit_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    summary: Mapped[str | None] = mapped_column(String(512), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    creator_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("idx_category", "category"),
        Index("idx_status", "status"),
        Index("idx_creator", "creator_id"),
    )


class UnitPermissionRecord(BaseORM):
    """unit_permissions 表 —— 知识四维权限（global / department / role / user）。"""

    __tablename__ = "unit_permissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    unit_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("knowledge_units.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_unit", "unit_id"),
        Index("idx_target", "target_type", "target_id"),
        CheckConstraint(
            "(target_type = 'global' AND target_id IS NULL) OR "
            "(target_type = 'department' AND target_id IS NOT NULL) OR "
            "(target_type = 'role' AND target_id IS NOT NULL) OR "
            "(target_type = 'user' AND target_id IS NOT NULL)",
            name="chk_target_consistency",
        ),
    )


# ════════════════════════════════════════════════════════════
# AI 问答域（2 张）
# ════════════════════════════════════════════════════════════


class QaAccessLogRecord(BaseORM):
    """qa_access_logs 表 —— 问答日志（看板 + 缺口识别数据源）。"""

    __tablename__ = "qa_access_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(MEDIUMTEXT, nullable=True)
    recalled_unit_ids_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    authorized_unit_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    unauthorized_unit_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, server_default="llm")
    related_unit_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_session", "session_id"),
        Index("idx_user", "user_id"),
        Index("idx_created", "created_at"),
        Index("idx_question", "question", mysql_length=64),
        Index("idx_source", "source"),
        Index("idx_source_unit", "source", "related_unit_id"),
    )


class ChatSessionRecord(BaseORM):
    """chat_sessions 表 —— 多轮会话（UUID 由客户端生成）。"""

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    history_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (Index("idx_user_updated", "user_id", "updated_at"),)


# ════════════════════════════════════════════════════════════
# 知识沉淀域（2 张）
# ════════════════════════════════════════════════════════════


class FaqRecord(BaseORM):
    """faqs 表 —— FAQ 标准问答（含 Redis 缓存同步）。"""

    __tablename__ = "faqs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    question_hash: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    answer: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    related_unit_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("knowledge_units.id"), nullable=True
    )
    unit_updated_at_snapshot: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending_review")
    hit_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    reviewer_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("idx_status", "status"),
        Index("idx_source", "source_type"),
        Index("idx_related_unit", "related_unit_id"),
    )


class KnowledgeGapRecord(BaseORM):
    """knowledge_gaps 表 —— 知识缺口识别（一键建档数据源）。"""

    __tablename__ = "knowledge_gaps"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    question_pattern: Mapped[str] = mapped_column(String(255), nullable=False)
    question_pattern_hash: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    sample_questions_json: Mapped[list] = mapped_column(JSON, nullable=False)
    ask_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    last_asked_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="unresolved")
    resolved_unit_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("knowledge_units.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("idx_status", "status"),
        Index("idx_last_asked", "last_asked_at"),
        Index("idx_resolved_unit", "resolved_unit_id"),
    )


# ════════════════════════════════════════════════════════════
# 引擎 + SessionLocal + Depends
# ════════════════════════════════════════════════════════════

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """返回全局 AsyncEngine 单例（首次调用时创建）。"""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """返回全局 async_sessionmaker 单例。"""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：每个请求一个 session，结束自动 close。"""
    factory = get_session_factory()
    async with factory() as session:
        yield session


# 用于类型标注的 Depends 别名（FastAPI 注解）
DbSessionDep = Depends(get_db)
