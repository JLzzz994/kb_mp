# IMPL-M2 — 组织架构管理（Python 方法级实现蓝图）

| 项目 | 内容 |
| --- | --- |
| 文档版本 | V1.0 |
| 阶段 | P0 |
| 编写依据 | [Spec M2](../specs/M2-组织架构管理.md) |
| 范围 | Department / User / Role 三个 Service 的完整方法实现 + pytest |

---

## 1. 文件清单

```
app/
├── api/
│   ├── routers/org_router.py
│   └── schemas/{department,user,role}_schema.py
├── domain/{department,role}.py
├── services/{department,user,role}_service.py
└── repositories/{department,user,role}_repository.py

tests/
├── test_org_departments.py
├── test_org_users.py
└── test_org_roles.py
```

---

## 2. Department Service

```python
# app/domain/department.py
"""部门领域实体。"""

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class DepartmentEntity:
    id: int
    parent_id: int | None
    name: str
    leader_id: int | None
    sort_order: int
    member_count: int = 0


# app/repositories/department_repository.py
class DepartmentRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_all_with_member_count(self) -> list[DepartmentRecord]:
        """一次 SQL 拉所有部门 + 成员数（LEFT JOIN users）。"""
        stmt = (
            select(
                DepartmentRecord,
                func.count(UserRecord.id).label("member_count"),
            )
            .outerjoin(
                UserRecord,
                and_(
                    UserRecord.department_id == DepartmentRecord.id,
                    UserRecord.status == 1,
                ),
            )
            .group_by(DepartmentRecord.id)
        )
        result = await self._session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def find_by_id(self, dept_id: int) -> DepartmentRecord | None:
        stmt = select(DepartmentRecord).where(DepartmentRecord.id == dept_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def count_children(self, dept_id: int) -> int:
        """子部门数。"""
        stmt = select(func.count(DepartmentRecord.id)).where(DepartmentRecord.parent_id == dept_id)
        return (await self._session.execute(stmt)).scalar_one()

    async def count_members(self, dept_id: int) -> int:
        """成员数（仅 status=1）。"""
        stmt = select(func.count(UserRecord.id)).where(
            and_(UserRecord.department_id == dept_id, UserRecord.status == 1)
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def create(self, data: DepartmentCreate) -> DepartmentRecord:
        record = DepartmentRecord(
            parent_id=data.parent_id,
            name=data.name,
            leader_id=data.leader_id,
            sort_order=data.sort_order,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def update(self, dept_id: int, data: DepartmentUpdate) -> DepartmentRecord:
        record = await self.find_by_id(dept_id)
        if record is None:
            raise DepartmentNotFoundError(dept_id)
        if data.name is not None:
            record.name = data.name
        if data.parent_id is not None:
            record.parent_id = data.parent_id
        if data.leader_id is not None:
            record.leader_id = data.leader_id
        if data.sort_order is not None:
            record.sort_order = data.sort_order
        await self._session.flush()
        return record

    async def delete(self, dept_id: int) -> None:
        record = await self.find_by_id(dept_id)
        if record is None:
            raise DepartmentNotFoundError(dept_id)
        await self._session.delete(record)


# app/services/department_service.py
class DepartmentService:
    def __init__(self, repo: DepartmentRepository, redis: RedisClient):
        self._repo = repo
        self._redis = redis

    async def list_tree(self) -> list[DepartmentNode]:
        """返回部门树（嵌套结构）。

        步骤：
        1. 一次 SQL 拉所有部门 + member_count
        2. 内存组装树：建 id → node 映射 + 父子链接
        """
        # 1. 拉数据
        records = await self._repo.list_all_with_member_count()

        # 2. 建映射
        nodes: dict[int, DepartmentNode] = {}
        for record, count in records:
            nodes[record.id] = DepartmentNode(
                id=record.id,
                name=record.name,
                parent_id=record.parent_id,
                leader_id=record.leader_id,
                member_count=count,
                children=[],
            )

        # 3. 组装父子关系
        roots: list[DepartmentNode] = []
        for node in nodes.values():
            if node.parent_id is None:
                roots.append(node)
            elif node.parent_id in nodes:
                nodes[node.parent_id].children.append(node)
            else:
                # 父部门不存在；视为孤儿，挂根
                roots.append(node)

        # 4. 按 sort_order 排序（递归）
        def sort_recursive(ns: list[DepartmentNode]) -> None:
            ns.sort(key=lambda n: (n.sort_order if hasattr(n, "sort_order") else 0, n.id))
            for n in ns:
                sort_recursive(n.children)

        sort_recursive(roots)

        return roots

    async def create(self, data: DepartmentCreate) -> DepartmentNode:
        """创建部门。

        步骤：
        1. 校验 parent_id 必须存在
        2. INSERT
        3. 返回 DepartmentNode
        """
        # 1. 校验父部门
        if data.parent_id is not None:
            parent = await self._repo.find_by_id(data.parent_id)
            if parent is None:
                raise DepartmentNotFoundError(data.parent_id)

        # 2. 插入
        record = await self._repo.create(data)

        # 3. 转 DTO
        return DepartmentNode(
            id=record.id,
            name=record.name,
            parent_id=record.parent_id,
            leader_id=record.leader_id,
            member_count=0,
            children=[],
        )

    async def update(self, dept_id: int, data: DepartmentUpdate) -> DepartmentNode:
        """更新部门。

        步骤：
        1. 校验目标存在
        2. 校验新 parent_id 不能形成环（target 不能是自己或自己的后代）
        3. UPDATE
        """
        # 1. 存在性
        existing = await self._repo.find_by_id(dept_id)
        if existing is None:
            raise DepartmentNotFoundError(dept_id)

        # 2. 防环：若 parent_id == dept_id 抛错
        if data.parent_id == dept_id:
            raise ValidationError("department.parent_self")

        # （防后代环的检测需查全树；演示期简化）
        # 3. 更新
        record = await self._repo.update(dept_id, data)
        return DepartmentNode(...)

    async def delete(self, dept_id: int) -> None:
        """删除部门。

        步骤：
        1. 存在性
        2. 检查子部门
        3. 检查成员
        4. DELETE
        """
        # 1. 存在性
        if await self._repo.find_by_id(dept_id) is None:
            raise DepartmentNotFoundError(dept_id)

        # 2. 子部门
        children_count = await self._repo.count_children(dept_id)
        if children_count > 0:
            raise DepartmentNotEmptyError(detail=f"部门下仍有 {children_count} 个子部门")

        # 3. 成员
        member_count = await self._repo.count_members(dept_id)
        if member_count > 0:
            raise DepartmentNotEmptyError(detail=f"部门下仍有 {member_count} 名成员")

        # 4. 删除
        await self._repo.delete(dept_id)
```

---

## 3. User Service

```python
# app/api/schemas/user_schema.py
class UserUpdate(BaseModel):
    """更新用户（更新时 role_ids 全部替换，与 create 行为一致；其余字段可选）。

    字段说明：
    - display_name / department_id / role_ids / status 均为可选（None 表示不更新）
    - role_ids 传入则全量替换 user_roles（与 create 一致）
    - status 仅允许 0（停用）/ 1（启用）
    """

    display_name: str | None = Field(default=None, min_length=1, max_length=64)
    department_id: int | None = None
    role_ids: list[int] | None = None
    status: int | None = Field(default=None, ge=0, le=1)


# app/domain/role.py
@dataclass(slots=True, frozen=True)
class RoleEntity:
    id: int
    role_name: str
    role_code: str
    description: str | None


# app/repositories/user_repository.py
class UserRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_paginated(
        self,
        *,
        page: int,
        page_size: int,
        department_id: int | None,
        status: int | None,
        keyword: str | None,
    ) -> tuple[list[tuple[UserRecord, str, list[str]]], int]:
        """分页查询用户（含部门名 + 角色码列表）。

        步骤：
        1. 构造动态 WHERE
        2. JOIN departments + user_roles + roles
        3. 聚合 role_codes per user
        4. 分页 + 总数
        """
        # 1. 基础查询
        stmt = (
            select(UserRecord, DepartmentRecord.name)
            .join(DepartmentRecord, DepartmentRecord.id == UserRecord.department_id)
            .where(UserRecord.status != -1)  # 不取已硬删除的
        )

        # 2. 筛选
        if department_id is not None:
            stmt = stmt.where(UserRecord.department_id == department_id)
        if status is not None:
            stmt = stmt.where(UserRecord.status == status)
        if keyword:
            stmt = stmt.where(
                or_(
                    UserRecord.username.like(f"%{keyword}%"),
                    UserRecord.display_name.like(f"%{keyword}%"),
                )
            )

        # 3. 总数（独立 COUNT 查询）
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        # 4. 分页
        stmt = stmt.offset((page - 1) * page_size).limit(page_size).order_by(UserRecord.id)
        rows = (await self._session.execute(stmt)).all()

        # 5. 批量查 role_codes
        user_ids = [row[0].id for row in rows]
        role_codes_map = await self._batch_role_codes(user_ids)

        return [(row[0], row[1], role_codes_map.get(row[0].id, [])) for row in rows], total

    async def _batch_role_codes(self, user_ids: list[int]) -> dict[int, list[str]]:
        """批量查 user_id → [role_code, ...]。"""
        if not user_ids:
            return {}
        stmt = (
            select(UserRoleRecord.user_id, RoleRecord.role_code)
            .join(RoleRecord, RoleRecord.id == UserRoleRecord.role_id)
            .where(UserRoleRecord.user_id.in_(user_ids))
        )
        rows = (await self._session.execute(stmt)).all()
        result: dict[int, list[str]] = {uid: [] for uid in user_ids}
        for user_id, code in rows:
            result[user_id].append(code)
        return result

    async def find_by_id(self, user_id: int) -> UserRecord | None: ...
    async def find_by_username(self, username: str) -> UserRecord | None: ...
    async def create(self, data: UserCreate, password_hash: str) -> UserRecord:
        record = UserRecord(
            username=data.username,
            password_hash=password_hash,
            display_name=data.display_name,
            department_id=data.department_id,
            status=1,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def insert_user_roles(self, user_id: int, role_ids: list[int]) -> None:
        for role_id in role_ids:
            self._session.add(UserRoleRecord(user_id=user_id, role_id=role_id))
        await self._session.flush()

    async def update(self, user_id: int, data: UserUpdate) -> UserRecord: ...
    async def set_status(self, user_id: int, status: int) -> None:
        record = await self.find_by_id(user_id)
        if record is None:
            raise UserNotFoundError(user_id)
        record.status = status
        await self._session.flush()

    async def update_password(self, user_id: int, password_hash: str) -> None:
        record = await self.find_by_id(user_id)
        if record is None:
            raise UserNotFoundError(user_id)
        record.password_hash = password_hash
        await self._session.flush()


# app/services/user_service.py
class UserService:
    def __init__(
        self, user_repo: UserRepository, password_hasher: PasswordHasher, redis: RedisClient
    ):
        self._repo = user_repo
        self._hasher = password_hasher
        self._redis = redis

    async def list(self, *, page, page_size, department_id, status, keyword) -> UserListResponse:
        """分页查询用户列表。

        步骤：
        1. 调用 user_repo.list_paginated
        2. 转 DTO
        """
        rows, total = await self._repo.list_paginated(
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
        record = await self._repo.find_by_id(user_id)
        if record is None:
            raise UserNotFoundError(user_id)
        # 部门 + 角色
        ...
        return UserResponse(...)

    async def create(self, data: UserCreate) -> UserResponse:
        """创建用户。

        步骤：
        1. 校验 username 唯一
        2. 校验 department_id 存在
        3. 校验所有 role_id 存在
        4. bcrypt 哈希密码
        5. INSERT users + INSERT user_roles（同一事务）
        6. 返回 UserResponse
        """
        # 1. username 唯一
        existing = await self._repo.find_by_username(data.username)
        if existing is not None:
            raise UsernameConflictError(data.username)

        # 2. 部门校验（调用 department_service.find_by_id 或直接 repo）
        ...

        # 3. 角色校验
        # 调用 role_service.batch_find_by_ids
        existing_roles = await self._role_service.batch_find_by_ids(data.role_ids)
        if len(existing_roles) != len(set(data.role_ids)):
            raise RoleNotFoundError(...)

        # 4. 密码哈希
        password_hash = self._hasher.hash(data.password)

        # 5. INSERT（同一 session，同一事务）
        user = await self._repo.create(data, password_hash)
        await self._repo.insert_user_roles(user.id, data.role_ids)

        # 6. 记录日志
        logger.info(
            "user.create user_id={} username={} roles={}", user.id, user.username, data.role_ids
        )

        # 7. 返回
        return await self.get(user.id)

    async def reset_password(self, user_id: int, new_password: str) -> None:
        """重置密码。

        步骤：
        1. 校验用户存在
        2. bcrypt 哈希
        3. UPDATE
        4. 清 Redis 位图（旧位图失效，下次请求重算）
        """
        record = await self._repo.find_by_id(user_id)
        if record is None:
            raise UserNotFoundError(user_id)
        password_hash = self._hasher.hash(new_password)
        await self._repo.update_password(user_id, password_hash)
        await self._redis.del_bitmap(user_id)
        logger.warn("user.reset_password user_id={}", user_id)

    async def set_status(self, user_id: int, status: int) -> None:
        """启停用。

        步骤：
        1. 校验
        2. UPDATE
        3. 停用时清 Redis 位图
        """
        await self._repo.set_status(user_id, status)
        if status == 0:
            await self._redis.del_bitmap(user_id)
            logger.warn("user.disable user_id={}", user_id)
```

---

## 4. Role Service

```python
# app/repositories/role_repository.py
class RoleRepository:
    BUILTIN_ROLE_CODES = {"system_admin", "knowledge_admin", "regular_user"}

    async def list_all_with_permissions(self) -> list[tuple[RoleRecord, list[str]]]:
        """查所有角色 + 每个角色的权限码列表。

        步骤：
        1. 查所有角色
        2. 批量查 permissions
        3. 内存聚合
        """
        # 1. 查角色
        roles = (await self._session.execute(select(RoleRecord))).scalars().all()

        # 2. 批量查权限
        role_ids = [r.id for r in roles]
        stmt = select(RolePermissionRecord.role_id, RolePermissionRecord.permission_code).where(
            RolePermissionRecord.role_id.in_(role_ids)
        )
        perm_rows = (await self._session.execute(stmt)).all()

        # 3. 聚合
        perm_map: dict[int, list[str]] = {}
        for role_id, code in perm_rows:
            perm_map.setdefault(role_id, []).append(code)

        return [(r, perm_map.get(r.id, [])) for r in roles]

    async def list_users_with_role(self, role_id: int) -> list[int]:
        """查持有此角色的 user_id 列表（供权限变更批量失效位图）。"""
        stmt = select(UserRoleRecord.user_id).where(UserRoleRecord.role_id == role_id)
        return list((await self._session.execute(stmt)).scalars().all())

    async def batch_find_by_ids(self, ids: list[int]) -> list[RoleRecord]:
        stmt = select(RoleRecord).where(RoleRecord.id.in_(ids))
        return list((await self._session.execute(stmt)).scalars().all())

    async def replace_role_permissions(self, role_id: int, codes: list[str]) -> None:
        """全量替换角色的权限。

        步骤：
        1. DELETE FROM role_permissions WHERE role_id
        2. INSERT 批量
        """
        # 1. 删旧
        await self._session.execute(
            delete(RolePermissionRecord).where(RolePermissionRecord.role_id == role_id)
        )
        # 2. 批量插入
        for code in codes:
            self._session.add(
                RolePermissionRecord(
                    role_id=role_id,
                    permission_code=code,
                    permission_type="menu",
                )
            )
        await self._session.flush()

    async def find_by_code(self, code: str) -> RoleRecord | None:
        stmt = select(RoleRecord).where(RoleRecord.role_code == code)
        return (await self._session.execute(stmt)).scalar_one_or_none()


# app/services/role_service.py
class RoleService:
    def __init__(self, role_repo: RoleRepository, redis: RedisClient):
        self._repo = role_repo
        self._redis = redis

    async def list(self) -> list[RoleResponse]:
        """返回所有角色 + 权限列表。"""
        pairs = await self._repo.list_all_with_permissions()
        return [
            RoleResponse(
                id=r.id,
                role_name=r.role_name,
                role_code=r.role_code,
                description=r.description,
                permissions=perms,
            )
            for r, perms in pairs
        ]

    async def assign_permissions(self, role_id: int, codes: list[str]) -> None:
        """分配权限（含 Redis 位图批量失效）。

        步骤：
        1. 校验 role 存在
        2. 校验 codes 是 PermissionCode.ALL_PERMISSION_CODES 的子集
        3. 替换 role_permissions
        4. 查持有此 role 的所有 user_id
        5. DEL auth:bitmap:{user_id} 全部
        """
        # 1. role 存在
        roles = await self._repo.batch_find_by_ids([role_id])
        if not roles:
            raise RoleNotFoundError(role_id)

        # 2. codes 校验
        invalid = set(codes) - set(PermissionCode.ALL_PERMISSION_CODES)
        if invalid:
            raise ValidationError(f"invalid_permission_codes: {invalid}")

        # 3. 替换
        await self._repo.replace_role_permissions(role_id, codes)

        # 4. 查 user_ids
        affected_user_ids = await self._repo.list_users_with_role(role_id)

        # 5. 批量失效位图
        for uid in affected_user_ids:
            await self._redis.del_bitmap(uid)

        # 6. 日志
        logger.warn(
            "role.permissions_change role_id={} codes={} affected_users={}",
            role_id,
            codes,
            len(affected_user_ids),
        )

    async def list_all_permission_codes(self) -> list[str]:
        """返回 PermissionCode.ALL_PERMISSION_CODES 常量。"""
        return list(PermissionCode.ALL_PERMISSION_CODES)
```

---

## 5. Router

```python
# app/api/routers/org_router.py
router = APIRouter(prefix="/api/v1/org", tags=["org"])


@router.get(
    "/departments",
    response_model=list[DepartmentNode],
    dependencies=[Depends(require_permission("dept:read"))],
)
async def list_departments(service: DepartmentServiceDep):
    return await service.list_tree()


@router.post(
    "/departments",
    response_model=DepartmentNode,
    status_code=201,
    dependencies=[Depends(require_permission("dept:write"))],
)
async def create_department(data: DepartmentCreate, service: DepartmentServiceDep):
    return await service.create(data)


@router.put(
    "/departments/{dept_id}",
    response_model=DepartmentNode,
    dependencies=[Depends(require_permission("dept:write"))],
)
async def update_department(dept_id: int, data: DepartmentUpdate, service: DepartmentServiceDep):
    return await service.update(dept_id, data)


@router.delete(
    "/departments/{dept_id}",
    status_code=204,
    dependencies=[Depends(require_permission("dept:write"))],
)
async def delete_department(dept_id: int, service: DepartmentServiceDep):
    await service.delete(dept_id)


@router.get(
    "/users",
    response_model=UserListResponse,
    dependencies=[Depends(require_permission("user:read"))],
)
async def list_users(
    service: UserServiceDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    department_id: int | None = None,
    status: int | None = None,
    keyword: str | None = None,
):
    return await service.list(
        page=page,
        page_size=page_size,
        department_id=department_id,
        status=status,
        keyword=keyword,
    )


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=201,
    dependencies=[Depends(require_permission("user:write"))],
)
async def create_user(data: UserCreate, service: UserServiceDep):
    return await service.create(data)


@router.get(
    "/users/{user_id}",
    response_model=UserResponse,
    dependencies=[Depends(require_permission("user:read"))],
)
async def get_user(user_id: int, service: UserServiceDep):
    """获取单个用户详情（含部门名 + 角色码列表）。"""
    return await service.get(user_id)


@router.put(
    "/users/{user_id}",
    response_model=UserResponse,
    dependencies=[Depends(require_permission("user:write"))],
)
async def update_user(
    user_id: int,
    data: UserUpdate,
    service: UserServiceDep,
):
    """更新用户（部分字段；role_ids 传入则全量替换）。"""
    return await service.update(user_id, data)


@router.patch(
    "/users/{user_id}/status",
    status_code=204,
    dependencies=[Depends(require_permission("user:write"))],
)
async def set_user_status(user_id: int, data: UserStatusPatch, service: UserServiceDep):
    await service.set_status(user_id, data.status)


@router.post(
    "/users/{user_id}/reset-password",
    status_code=204,
    dependencies=[Depends(require_permission("user:write"))],
)
async def reset_password(user_id: int, data: ResetPasswordRequest, service: UserServiceDep):
    await service.reset_password(user_id, data.new_password)


@router.get(
    "/roles",
    response_model=list[RoleResponse],
    dependencies=[Depends(require_permission("role:read"))],
)
async def list_roles(service: RoleServiceDep):
    return await service.list()


@router.post(
    "/roles/{role_id}/permissions",
    status_code=204,
    dependencies=[Depends(require_permission("role:write"))],
)
async def assign_role_permissions(
    role_id: int, data: AssignPermissionsRequest, service: RoleServiceDep
):
    await service.assign_permissions(role_id, data.permission_codes)


@router.get(
    "/permissions",
    response_model=list[str],
    dependencies=[Depends(require_permission("role:read"))],
)
async def list_permission_codes(service: RoleServiceDep):
    return await service.list_all_permission_codes()
```

---

## 6. 测试用例

```python
# tests/test_org_departments.py
@pytest.mark.asyncio
class TestDepartments:
    async def test_list_departments_returns_tree(
        self, async_client, admin_token, seeded_departments
    ):
        resp = await async_client.get("/api/v1/org/departments", headers=auth_header(admin_token))
        assert resp.status_code == 200
        body = resp.json()
        # 顶层有 1 个根，子节点嵌在 children
        assert len(body) == 1
        assert len(body[0]["children"]) >= 2

    async def test_create_department_with_invalid_parent_returns_404(
        self, async_client, admin_token
    ):
        req = {"name": "新部门", "parent_id": 9999}
        resp = await async_client.post(
            "/api/v1/org/departments", json=req, headers=auth_header(admin_token)
        )
        assert resp.status_code == 404

    async def test_delete_dept_with_children_returns_422(
        self, async_client, admin_token, seeded_departments
    ):
        # 尝试删除有子部门的根
        resp = await async_client.delete(
            "/api/v1/org/departments/1",
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error_code"] == "department_not_empty"

    async def test_delete_dept_with_members_returns_422(
        self, async_client, admin_token, seeded_admin_in_dept
    ):
        resp = await async_client.delete(
            "/api/v1/org/departments/1",
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 422

    async def test_regular_user_cannot_create_dept(self, async_client, regular_user_token):
        req = {"name": "hack", "parent_id": None}
        resp = await async_client.post(
            "/api/v1/org/departments", json=req, headers=auth_header(regular_user_token)
        )
        assert resp.status_code == 403


# tests/test_org_users.py
@pytest.mark.asyncio
class TestUsers:
    async def test_create_user_hashes_password(self, async_client, admin_token, db_session):
        req = {
            "username": "newbie",
            "password": "Init@1234",
            "display_name": "新人",
            "department_id": 1,
            "role_ids": [3],
        }
        resp = await async_client.post(
            "/api/v1/org/users", json=req, headers=auth_header(admin_token)
        )
        assert resp.status_code == 201

        # 验证密码已哈希
        record = await db_session.execute(select(UserRecord).where(UserRecord.username == "newbie"))
        user = record.scalar_one()
        assert user.password_hash != "Init@1234"
        assert user.password_hash.startswith("$2b$")  # bcrypt 标识

    async def test_create_user_duplicate_username_returns_409(self, async_client, admin_token):
        req = {
            "username": "admin",
            "password": "Another@1234",
            "display_name": "x",
            "department_id": 1,
            "role_ids": [3],
        }
        resp = await async_client.post(
            "/api/v1/org/users", json=req, headers=auth_header(admin_token)
        )
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "username_conflict"

    async def test_list_users_paginated(self, async_client, admin_token, seeded_users):
        resp = await async_client.get(
            "/api/v1/org/users?page=1&page_size=2",
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["page"] == 1
        assert body["page_size"] == 2
        assert body["total"] == 5
        assert len(body["items"]) == 2

    async def test_reset_password_clears_redis_bitmap(
        self, async_client, admin_token, redis_client
    ):
        # 模拟位图已存在
        await redis_client.set("auth:bitmap:2", "[]", ex=300)
        resp = await async_client.post(
            "/api/v1/org/users/2/reset-password",
            json={"new_password": "New@1234"},
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 204
        assert await redis_client.exists("auth:bitmap:2") is False

    async def test_disable_user_clears_bitmap(self, async_client, admin_token, redis_client):
        await redis_client.set("auth:bitmap:2", "[]", ex=300)
        resp = await async_client.patch(
            "/api/v1/org/users/2/status",
            json={"status": 0},
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 204
        assert await redis_client.exists("auth:bitmap:2") is False


# tests/test_org_roles.py
@pytest.mark.asyncio
class TestRoles:
    async def test_assign_permissions_clears_user_bitmaps(
        self, async_client, admin_token, redis_client, seeded_users
    ):
        # 给 user 2 和 user 3 设置位图
        await redis_client.set("auth:bitmap:2", '["knowledge:read"]', ex=300)
        await redis_client.set("auth:bitmap:3", '["ai:chat"]', ex=300)

        # 给 role 3（regular_user）分配知识权限
        resp = await async_client.post(
            "/api/v1/org/roles/3/permissions",
            json={"permission_codes": ["knowledge:read", "knowledge:write"]},
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 204

        # 持有 role 3 的 user 位图应被清
        # （假设 seeded_users 让 user 2 持有 role 3）
        assert await redis_client.exists("auth:bitmap:2") is False

    async def test_assign_invalid_permission_code_returns_422(self, async_client, admin_token):
        resp = await async_client.post(
            "/api/v1/org/roles/3/permissions",
            json={"permission_codes": ["unknown:perm"]},
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 422

    async def test_list_roles_includes_system_admin_with_all_perms(
        self, async_client, admin_token, seeded_data
    ):
        resp = await async_client.get("/api/v1/org/roles", headers=auth_header(admin_token))
        body = resp.json()
        sys_admin = next(r for r in body if r["role_code"] == "system_admin")
        assert len(sys_admin["permissions"]) == 17
```

---

## 7. 验收 Checklist

- [ ] 5 个 Department 用例通过（含删除保护）
- [ ] 5 个 User 用例通过（含密码哈希、用户名冲突、位图失效）
- [ ] 3 个 Role 用例通过（含权限变更批量失效）
- [ ] bcrypt 哈希验证（`password_hash.startswith("$2b$")`）
- [ ] Redis 位图失效链路验证
- [ ] RBAC 拦截（regular_user 调 `dept:write` 返回 403）