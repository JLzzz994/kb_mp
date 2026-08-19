"""DepartmentService：部门树组装 + CRUD + 删除保护。"""

from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.department_schema import (
    DepartmentCreate,
    DepartmentNode,
    DepartmentUpdate,
)
from app.common.errors import DepartmentNotEmptyError, DepartmentNotFoundError
from app.repositories.department_repository import DepartmentRepository


class DepartmentService:
    def __init__(self, repo: DepartmentRepository, session: AsyncSession) -> None:
        self._repo = repo
        self._session = session

    async def list_tree(self) -> list[DepartmentNode]:
        """拉全表 + 一次 COUNT 聚合 + 内存组装嵌套树（避免 N+1）。"""
        rows = await self._repo.list_all()
        counts = await self._repo.count_members_by_dept()

        # 一次性把所有节点建出来，按 id 索引
        nodes: dict[int, DepartmentNode] = {
            r.id: DepartmentNode(
                id=r.id,
                parent_id=r.parent_id,
                name=r.name,
                leader_id=r.leader_id,
                sort_order=r.sort_order,
                member_count=counts.get(r.id, 0),
                children=[],
            )
            for r in rows
        }

        # 拼父子（稳定排序已在 SQL 完成）
        roots: list[DepartmentNode] = []
        for node in nodes.values():
            if node.parent_id is None or node.parent_id not in nodes:
                roots.append(node)
            else:
                nodes[node.parent_id].children.append(node)
        return roots

    async def create(self, data: DepartmentCreate) -> DepartmentNode:
        """创建部门。parent_id 必须存在（None 表示顶级）。"""
        if data.parent_id is not None:
            parent = await self._repo.find_by_id(data.parent_id)
            if parent is None:
                raise DepartmentNotFoundError(f"parent_id={data.parent_id}")
        row = await self._repo.create(
            name=data.name,
            parent_id=data.parent_id,
            leader_id=data.leader_id,
            sort_order=data.sort_order,
        )
        await self._session.commit()
        logger.info("department.create dept_id={} name={}", row.id, row.name)
        return DepartmentNode(
            id=row.id,
            parent_id=row.parent_id,
            name=row.name,
            leader_id=row.leader_id,
            sort_order=row.sort_order,
            member_count=0,
            children=[],
        )

    async def update(self, dept_id: int, data: DepartmentUpdate) -> DepartmentNode:
        """全量更新。目标 id 不存在 → 404；新 parent_id 不存在 → 404。"""
        if await self._repo.find_by_id(dept_id) is None:
            raise DepartmentNotFoundError(f"id={dept_id}")
        if data.parent_id is not None:
            parent = await self._repo.find_by_id(data.parent_id)
            if parent is None:
                raise DepartmentNotFoundError(f"parent_id={data.parent_id}")
        row = await self._repo.update(
            dept_id,
            name=data.name,
            parent_id=data.parent_id,
            leader_id=data.leader_id,
            sort_order=data.sort_order,
        )
        if row is None:  # 并发删除的极端竞态
            raise DepartmentNotFoundError(f"id={dept_id}")
        await self._session.commit()
        logger.info("department.update dept_id={} name={}", row.id, row.name)
        return DepartmentNode(
            id=row.id,
            parent_id=row.parent_id,
            name=row.name,
            leader_id=row.leader_id,
            sort_order=row.sort_order,
            member_count=0,
            children=[],
        )

    async def delete(self, dept_id: int) -> None:
        """删除部门。子部门或成员存在 → 422。目标不存在 → 404。"""
        if await self._repo.find_by_id(dept_id) is None:
            raise DepartmentNotFoundError(f"id={dept_id}")
        if await self._repo.has_children(dept_id):
            raise DepartmentNotEmptyError(f"dept_id={dept_id} has children")
        if await self._repo.has_members(dept_id):
            raise DepartmentNotEmptyError(f"dept_id={dept_id} has members")
        await self._repo.delete(dept_id)
        await self._session.commit()
        logger.info("department.delete dept_id={}", dept_id)


# ── DI 工厂 ─────────────────────────────


def build_department_service(session) -> DepartmentService:
    return DepartmentService(DepartmentRepository(session), session)


__all__ = ["DepartmentService", "build_department_service"]
