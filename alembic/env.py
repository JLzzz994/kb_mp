"""Alembic env：使用项目内 settings.database_url，覆盖 alembic.ini 默认值。"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.config.settings import settings

# ── 导入所有 ORM 模型（确保 BaseORM.metadata 注册完整） ──
from app.infrastructure.database import (  # noqa: F401
    BaseORM,
    ChatSessionRecord,
    DepartmentRecord,
    FaqRecord,
    KnowledgeGapRecord,
    KnowledgeUnitRecord,
    QaAccessLogRecord,
    RolePermissionRecord,
    RoleRecord,
    UnitPermissionRecord,
    UserRecord,
    UserRoleRecord,
)

config = context.config

# 覆盖 sqlalchemy.url（aiomysql → pymysql，alembic 同步迁移）
config.set_main_option("sqlalchemy.url", settings.database_url.replace("+aiomysql", "+pymysql"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = BaseORM.metadata


def run_migrations_offline() -> None:
    """仅生成 SQL 脚本，不连接数据库。"""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """连接到数据库并应用迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
