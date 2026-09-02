"""慧策 ERP/WMS 产品知识运营平台数据库种子。

初始化产品、实施、客服、客户成功四类业务团队，以及系统管理员、知识管理员和业务查询用户。

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
    {"name": "产品中心", "parent_id": None, "sort_order": 0},
    {"name": "实施交付中心", "parent_id": None, "sort_order": 1},
    {"name": "商家客服中心", "parent_id": None, "sort_order": 2},
    {"name": "客户成功中心", "parent_id": None, "sort_order": 3},
]

ROLES = [
    {"role_name": "系统管理员", "role_code": "system_admin", "description": "平台与组织全权限"},
    {
        "role_name": "产品知识管理员",
        "role_code": "knowledge_admin",
        "description": "产品文档、FAQ、知识缺口与权限运营",
    },
    {
        "role_name": "业务查询用户",
        "role_code": "regular_user",
        "description": "实施、客服、客户成功的知识查询角色",
    },
]

KNOWLEDGE_ADMIN_CODES = [
    # 只读组织权限用于四维知识权限目标选择，不授予组织写权限。
    PermissionCode.USER_READ,
    PermissionCode.ROLE_READ,
    PermissionCode.DEPT_READ,
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
        "display_name": "平台管理员",
        "dept_index": 0,
        "role_code": "system_admin",
        "password": "Admin@123",
    },
    {
        "username": "kadmin",
        "display_name": "产品知识管理员",
        "dept_index": 0,
        "role_code": "knowledge_admin",
        "password": "Kadmin@123",
    },
    {
        "username": "alice",
        "display_name": "实施顾问演示用户",
        "dept_index": 1,
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
    """插入部门，返回 index → id 映射。"""
    index_to_id: dict[int, int] = {}
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
            index_to_id[i] = rec.id
        else:
            index_to_id[i] = existing.id
    await session.commit()
    return index_to_id


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
    """插入演示用户。"""
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
            existing.display_name = u["display_name"]
            existing.department_id = dept_ids[u["dept_index"]]
            await session.flush()

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
    parser = argparse.ArgumentParser(description="Huice ERP/WMS knowledge platform seed")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="先清表后重灌（默认仅插入缺失项）",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args.reset))


if __name__ == "__main__":
    main()
