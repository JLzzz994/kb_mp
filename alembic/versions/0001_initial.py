"""initial schema: 11 tables (auth/org/knowledge/chat/FAQ/gap)

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-19
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import MEDIUMTEXT

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ════════════════════════════════════════════════════════════
    # 组织权限域（5 张）
    # ════════════════════════════════════════════════════════════

    op.create_table(
        "departments",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "parent_id", sa.Integer, nullable=True
        ),  # FK → departments.id 自引用（循环，use_alter=True）
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("leader_id", sa.Integer, nullable=True),  # FK → users.id（循环，use_alter=True）
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_parent", "departments", ["parent_id"])
    op.create_index("idx_leader", "departments", ["leader_id"])
    # 循环 FK 用 ALTER TABLE 单独添加（推迟到 users 表创建之后）

    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(64), nullable=False),
        sa.Column("department_id", sa.Integer, nullable=False),  # FK via use_alter=True
        sa.Column("status", sa.SmallInteger, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_department", "users", ["department_id"])
    # 循环 FK（部门 ↔ 用户）— users 表已存在，可安全添加
    op.create_foreign_key(
        "fk_users_department_id",
        "users",
        "departments",
        ["department_id"],
        ["id"],
        use_alter=True,
    )
    op.create_foreign_key(
        "fk_departments_parent_id",
        "departments",
        "departments",
        ["parent_id"],
        ["id"],
        use_alter=True,
    )
    op.create_foreign_key(
        "fk_departments_leader_id",
        "departments",
        "users",
        ["leader_id"],
        ["id"],
        use_alter=True,
    )

    op.create_table(
        "roles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("role_name", sa.String(64), nullable=False),
        sa.Column("role_code", sa.String(64), nullable=False, unique=True),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )

    op.create_table(
        "user_roles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            sa.Integer,
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "role_id", name="uk_user_role"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_role", "user_roles", ["role_id"])

    op.create_table(
        "role_permissions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "role_id",
            sa.Integer,
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("permission_code", sa.String(64), nullable=False),
        sa.Column("permission_type", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("role_id", "permission_code", name="uk_role_perm"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_code", "role_permissions", ["permission_code"])

    # ════════════════════════════════════════════════════════════
    # 知识资产域（2 张）
    # ════════════════════════════════════════════════════════════

    op.create_table(
        "knowledge_units",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("unit_code", sa.String(32), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", MEDIUMTEXT, nullable=False),
        sa.Column("summary", sa.String(512), nullable=True),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("source_file_name", sa.String(255), nullable=True),
        sa.Column("file_type", sa.String(16), nullable=True),
        sa.Column("file_size", sa.BigInteger, nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True, unique=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("creator_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_category", "knowledge_units", ["category"])
    op.create_index("idx_status", "knowledge_units", ["status"])
    op.create_index("idx_creator", "knowledge_units", ["creator_id"])

    op.create_table(
        "unit_permissions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "unit_id",
            sa.Integer,
            sa.ForeignKey("knowledge_units.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_type", sa.String(16), nullable=False),
        sa.Column("target_id", sa.BigInteger, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "(target_type = 'global' AND target_id IS NULL) OR "
            "(target_type = 'department' AND target_id IS NOT NULL) OR "
            "(target_type = 'role' AND target_id IS NOT NULL) OR "
            "(target_type = 'user' AND target_id IS NOT NULL)",
            name="chk_target_consistency",
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_unit", "unit_permissions", ["unit_id"])
    op.create_index("idx_target", "unit_permissions", ["target_type", "target_id"])

    # ════════════════════════════════════════════════════════════
    # AI 问答域（2 张）
    # ════════════════════════════════════════════════════════════

    op.create_table(
        "qa_access_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("answer", MEDIUMTEXT, nullable=True),
        sa.Column("recalled_unit_ids_json", sa.JSON, nullable=True),
        sa.Column("authorized_unit_ids_json", sa.JSON, nullable=True),
        sa.Column("unauthorized_unit_ids_json", sa.JSON, nullable=True),
        sa.Column("prompt_tokens", sa.Integer, nullable=True),
        sa.Column("completion_tokens", sa.Integer, nullable=True),
        sa.Column("total_tokens", sa.Integer, nullable=True),
        sa.Column("response_time_ms", sa.Integer, nullable=True),
        sa.Column("source", sa.String(16), nullable=False, server_default="llm"),
        sa.Column("related_unit_id", sa.BigInteger, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_session", "qa_access_logs", ["session_id"])
    op.create_index("idx_user", "qa_access_logs", ["user_id"])
    op.create_index("idx_created", "qa_access_logs", ["created_at"])
    op.create_index("idx_question", "qa_access_logs", ["question"], mysql_length=64)
    op.create_index("idx_source", "qa_access_logs", ["source"])
    op.create_index("idx_source_unit", "qa_access_logs", ["source", "related_unit_id"])

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("history_json", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_user_updated", "chat_sessions", ["user_id", "updated_at"])

    # ════════════════════════════════════════════════════════════
    # 知识沉淀域（2 张）
    # ════════════════════════════════════════════════════════════

    op.create_table(
        "faqs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("question_hash", sa.String(40), nullable=False, unique=True),
        sa.Column("answer", MEDIUMTEXT, nullable=False),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column(
            "related_unit_id", sa.Integer, sa.ForeignKey("knowledge_units.id"), nullable=True
        ),
        sa.Column("unit_updated_at_snapshot", sa.DateTime, nullable=True),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending_review"),
        sa.Column("hit_count", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("reviewer_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_status_faq", "faqs", ["status"])
    op.create_index("idx_source_faq", "faqs", ["source_type"])
    op.create_index("idx_related_unit", "faqs", ["related_unit_id"])

    op.create_table(
        "knowledge_gaps",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("question_pattern", sa.String(255), nullable=False),
        sa.Column("question_pattern_hash", sa.String(40), nullable=False, unique=True),
        sa.Column("sample_questions_json", sa.JSON, nullable=False),
        sa.Column("ask_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "last_asked_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="unresolved"),
        sa.Column(
            "resolved_unit_id", sa.Integer, sa.ForeignKey("knowledge_units.id"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_status_gap", "knowledge_gaps", ["status"])
    op.create_index("idx_last_asked", "knowledge_gaps", ["last_asked_at"])
    op.create_index("idx_resolved_unit", "knowledge_gaps", ["resolved_unit_id"])


def downgrade() -> None:
    # 倒序删除（外键依赖）
    op.drop_table("knowledge_gaps")
    op.drop_table("faqs")
    op.drop_table("chat_sessions")
    op.drop_table("qa_access_logs")
    op.drop_table("unit_permissions")
    op.drop_table("knowledge_units")
    op.drop_table("role_permissions")
    op.drop_table("user_roles")
    op.drop_table("roles")
    op.drop_table("users")
    op.drop_table("departments")
