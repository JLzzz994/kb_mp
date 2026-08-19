"""kb_mp 数据库种子：3 部门 + 3 角色 + 17 权限码 + 3 用户。

> ADR-0003 决策 2：默认无参仅插入缺失项；--reset 清表后重灌。
> 使用方法：
>   python scripts/seed.py              # 增量
>   python scripts/seed.py --reset      # 清表 + 重灌
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.domain.permission import ALL_PERMISSION_CODES, PermissionCode
from app.infrastructure.database import (
    DepartmentRecord,
    RolePermissionRecord,
    RoleRecord,
    UserRecord,
    UserRoleRecord,
    get_session_factory,
)
from app.infrastructure.password_hasher import PasswordHasher

DEPARTMENTS = [
    {"name": "研发中心", "parent_id": None, "sort_order": 0},
    {"name": "产品部", "parent_id": None, "sort_order": 1},
    {"name": "运营部", "parent_id": None, "sort_order": 2},
]

ROLES = [
    {"role_name": "系统管理员", "role_code": "system_admin", "description": "全权限"},
    {"role_name": "知识管理员", "role_code": "knowledge_admin", "description": "知识管理子集"},
    {"role_name": "普通用户", "role_code": "regular_user", "description": "仅 AI + 知识查询"},
]

# 知识管理员权限（不含 user/role/dept 管理类）
KNOWLEDGE_ADMIN_CODES = [
    PermissionCode.KNOWLEDGE_READ,
    PermissionCode.KNOWLEDGE_WRITE,
    PermissionCode.KNOWLEDGE_DELETE,
    PermissionCode.KNOWLEDGE_ASSIGN_PERMISSION,
    PermissionCode.KNOWLEDGE_CHECK,
    PermissionCode.AI_CHAT,
    PermissionCode.DASHBOARD_READ,
    PermissionCode.FAQ_READ,
    PermissionCode.FAQ_WRITE,
    PermissionCode.FAQ_REVIEW,
    PermissionCode.GAP_READ,
]

REGULAR_USER_CODES = [
    PermissionCode.AI_CHAT,
    PermissionCode.KNOWLEDGE_READ,
    PermissionCode.FAQ_READ,
    PermissionCode.GAP_READ,
]

USERS = [
    {
        "username": "admin",
        "display_name": "系统管理员",
        "dept_index": 0,
        "role_code": "system_admin",
        "password": "Admin@123",
    },
    {
        "username": "kadmin",
        "display_name": "知识管理员",
        "dept_index": 0,
        "role_code": "knowledge_admin",
        "password": "Kadmin@123",
    },
    {
        "username": "alice",
        "display_name": "Alice",
        "dept_index": 2,
        "role_code": "regular_user",
        "password": "Alice@123",
    },
]


async def reset_all(session: AsyncSession) -> None:
    """清表（顺序：先依赖后被依赖）。"""
    for table in (UserRoleRecord, RolePermissionRecord, UserRecord, RoleRecord, DepartmentRecord):
        await session.execute(table.__table__.delete())
    await session.commit()


async def seed_departments(session: AsyncSession) -> dict[int, int]:
    """插入部门，返回 name → id 映射。"""
    name_to_id: dict[int, int] = {}
    for i, d in enumerate(DEPARTMENTS):
        existing = (
            await session.execute(
                select(DepartmentRecord).where(DepartmentRecord.name == d["name"])
            )
        ).scalar_one_or_none()
        if existing is None:
            rec = DepartmentRecord(
                parent_id=d["parent_id"],
                name=d["name"],
                leader_id=None,
                sort_order=d["sort_order"],
            )
            session.add(rec)
            await session.flush()
            name_to_id[i] = rec.id
        else:
            name_to_id[i] = existing.id
    await session.commit()
    return name_to_id


async def seed_roles(session: AsyncSession) -> dict[str, int]:
    """插入角色，返回 role_code → id 映射。"""
    code_to_id: dict[str, int] = {}
    for r in ROLES:
        existing = (
            await session.execute(select(RoleRecord).where(RoleRecord.role_code == r["role_code"]))
        ).scalar_one_or_none()
        if existing is None:
            rec = RoleRecord(
                role_name=r["role_name"],
                role_code=r["role_code"],
                description=r["description"],
            )
            session.add(rec)
            await session.flush()
            code_to_id[r["role_code"]] = rec.id
        else:
            code_to_id[r["role_code"]] = existing.id

        # 权限码（幂等：删除后重建）
        role_id = code_to_id[r["role_code"]]
        await session.execute(
            RolePermissionRecord.__table__.delete().where(RolePermissionRecord.role_id == role_id)
        )
        codes = (
            list(ALL_PERMISSION_CODES)
            if r["role_code"] == "system_admin"
            else KNOWLEDGE_ADMIN_CODES
            if r["role_code"] == "knowledge_admin"
            else REGULAR_USER_CODES
        )
        for c in codes:
            session.add(
                RolePermissionRecord(role_id=role_id, permission_code=c, permission_type="api")
            )
    await session.commit()
    return code_to_id


async def seed_users(
    session: AsyncSession,
    *,
    dept_ids: dict[int, int],
    role_ids: dict[str, int],
    hasher: PasswordHasher,
) -> None:
    """插入 3 个用户。"""
    for u in USERS:
        existing = (
            await session.execute(select(UserRecord).where(UserRecord.username == u["username"]))
        ).scalar_one_or_none()
        if existing is None:
            rec = UserRecord(
                username=u["username"],
                password_hash=hasher.hash(u["password"]),
                display_name=u["display_name"],
                department_id=dept_ids[u["dept_index"]],
                status=1,
            )
            session.add(rec)
            await session.flush()
            user_id = rec.id
        else:
            user_id = existing.id
            existing.password_hash = hasher.hash(u["password"])
            await session.flush()

        # user_roles（幂等）
        await session.execute(
            UserRoleRecord.__table__.delete().where(UserRoleRecord.user_id == user_id)
        )
        session.add(UserRoleRecord(user_id=user_id, role_id=role_ids[u["role_code"]]))
    await session.commit()


async def main_async(reset: bool) -> None:
    factory = get_session_factory()
    hasher = PasswordHasher()
    async with factory() as session:
        if reset:
            print("[seed] --reset: 清空全部表")
            await reset_all(session)
        dept_ids = await seed_departments(session)
        role_ids = await seed_roles(session)
        await seed_users(session, dept_ids=dept_ids, role_ids=role_ids, hasher=hasher)
    print(f"[seed] done (DB={settings.database_url.split('@')[-1]})")


def main() -> None:
    parser = argparse.ArgumentParser(description="kb_mp seed")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="先清表后重灌（默认仅插入缺失项）",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args.reset))


if __name__ == "__main__":
    main()
