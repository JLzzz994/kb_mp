"""UserService：用户 CRUD + 启停用 + 重置密码。"""

from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.user_schema import UserCreate, UserListResponse, UserResponse, UserUpdate
from app.common.errors import (
    DepartmentNotFoundError,
    RoleNotFoundError,
    UsernameConflictError,
    UserNotFoundError,
)
from app.infrastructure.database import DepartmentRecord
from app.infrastructure.password_hasher import PasswordHasher
from app.infrastructure.redis_client import RedisClient
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository


class UserService:
    def __init__(
        self,
        user_repo: UserRepository,
        role_repo: RoleRepository,
        hasher: PasswordHasher,
        redis: RedisClient,
        session: AsyncSession,
    ) -> None:
        self._user_repo = user_repo
        self._role_repo = role_repo
        self._hasher = hasher
        self._redis = redis
        self._session = session

    async def list(
        self,
        *,
        page: int,
        page_size: int,
        department_id: int | None,
        status: int | None,
        keyword: str | None,
    ) -> UserListResponse:
        rows, total = await self._user_repo.list_paginated(
            page=page,
            page_size=page_size,
            department_id=department_id,
            status=status,
            keyword=keyword,
        )
        items = [
            UserResponse(
                id=u.id,
                username=u.username,
                display_name=u.display_name,
                department_id=u.department_id,
                department_name=dept_name,
                role_codes=role_codes,
                status=u.status,
                created_at=u.created_at,
                updated_at=u.updated_at,
            )
            for u, dept_name, role_codes in rows
        ]
        return UserListResponse(items=items, page=page, page_size=page_size, total=total)

    async def get(self, user_id: int) -> UserResponse:
        record = await self._user_repo.find_by_id(user_id)
        if record is None:
            raise UserNotFoundError(f"id={user_id}")
        dept = (
            await self._session.execute(
                __import__("sqlalchemy")
                .select(DepartmentRecord)
                .where(DepartmentRecord.id == record.department_id)
            )
        ).scalar_one_or_none()
        role_codes = (await self._user_repo._batch_role_codes([user_id])).get(user_id, [])
        return UserResponse(
            id=record.id,
            username=record.username,
            display_name=record.display_name,
            department_id=record.department_id,
            department_name=dept.name if dept else "",
            role_codes=role_codes,
            status=record.status,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    async def create(self, data: UserCreate) -> UserResponse:
        # 1. username 唯一
        existing = await self._user_repo.find_by_username(data.username)
        if existing is not None:
            raise UsernameConflictError(data.username)
        if existing is not None:
            raise UsernameConflictError(data.username)

        # 2. 部门校验
        dept = (
            await self._session.execute(
                __import__("sqlalchemy")
                .select(DepartmentRecord)
                .where(DepartmentRecord.id == data.department_id)
            )
        ).scalar_one_or_none()
        if dept is None:
            raise DepartmentNotFoundError(f"id={data.department_id}")

        # 3. 角色校验
        roles = await self._role_repo.batch_find_by_ids(data.role_ids)
        if len(roles) != len(set(data.role_ids)):
            missing = set(data.role_ids) - {r.id for r in roles}
            raise RoleNotFoundError(f"missing role_ids={sorted(missing)}")

        # 4. 哈希
        password_hash = self._hasher.hash(data.password)

        # 5. INSERT users + user_roles（同一事务）
        user = await self._user_repo.create(
            username=data.username,
            password_hash=password_hash,
            display_name=data.display_name,
            department_id=data.department_id,
        )
        await self._user_repo.insert_user_roles(user.id, data.role_ids)
        await self._session.commit()

        logger.info("user.create user_id={} username={}", user.id, user.username)
        return await self.get(user.id)

    async def update(self, user_id: int, data: UserUpdate) -> UserResponse:
        existing = await self._user_repo.find_by_id(user_id)
        if existing is None:
            raise UserNotFoundError(f"id={user_id}")

        if (
            data.display_name is not None
            or data.department_id is not None
            or data.status is not None
        ):
            await self._user_repo.update(
                user_id,
                display_name=data.display_name,
                department_id=data.department_id,
                status=data.status,
            )

        if data.role_ids is not None:
            roles = await self._role_repo.batch_find_by_ids(data.role_ids)
            if len(roles) != len(set(data.role_ids)):
                missing = set(data.role_ids) - {r.id for r in roles}
                raise RoleNotFoundError(f"missing role_ids={sorted(missing)}")
            await self._user_repo.replace_user_roles(user_id, data.role_ids)

        await self._session.commit()

        # 角色 / 状态变更 → 清位图
        if data.role_ids is not None or data.status is not None:
            await self._redis.del_bitmap(user_id)

        return await self.get(user_id)

    async def set_status(self, user_id: int, status: int) -> None:
        record = await self._user_repo.set_status(user_id, status)
        if record is None:
            raise UserNotFoundError(f"id={user_id}")
        await self._session.commit()
        # 停用 → 清位图（防止已登录用户继续使用）
        await self._redis.del_bitmap(user_id)
        logger.warning("user.set_status user_id={} status={}", user_id, status)

    async def reset_password(self, user_id: int, new_password: str) -> None:
        password_hash = self._hasher.hash(new_password)
        record = await self._user_repo.update_password(user_id, password_hash)
        if record is None:
            raise UserNotFoundError(f"id={user_id}")
        await self._session.commit()
        # 清位图（旧密码的 token 立即失效——下次请求需重新登录）
        await self._redis.del_bitmap(user_id)
        logger.warning("user.reset_password user_id={}", user_id)


def build_user_service(
    session: AsyncSession,
    *,
    hasher: PasswordHasher,
    redis: RedisClient,
) -> UserService:
    return UserService(
        user_repo=UserRepository(session),
        role_repo=RoleRepository(session),
        hasher=hasher,
        redis=redis,
        session=session,
    )
