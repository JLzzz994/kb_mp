"""用户领域实体（dataclass，不依赖 ORM / FastAPI）。

> 三种类型分工（见 docs/CONTEXT.md §「用户」）：
> - UserEntity: 纯领域实体，无密码字段，无 ORM 依赖
> - UserWithPassword: 仅 Repository 内部使用（含 password_hash）
> - CurrentUser: 登录后注入请求上下文的最小主体（含 dept_ids + role_ids + permissions）
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class UserEntity:
    """纯领域实体，service 层使用。"""

    id: int
    username: str
    display_name: str
    department_id: int
    status: int  # 1=启用 / 0=停用


@dataclass(slots=True)
class UserWithPassword(UserEntity):
    """含密码哈希，仅 Repository 内部使用；禁止穿越到 service / router。"""

    password_hash: str


@dataclass(slots=True)
class CurrentUser:
    """登录后注入到 FastAPI Depends 的最小主体（鉴权 + 鉴权位图查询使用）。

    - role_codes / permissions: 缓存于 JWT payload + Redis 鉴权位图
    - dept_ids: 含当前部门 + 父部门（祖先继承），由 AuthService 在 login / load 时计算
    """

    id: int
    username: str
    display_name: str
    department_id: int
    role_codes: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    dept_ids: list[int] = field(default_factory=list)

    def has_permission(self, *codes: str) -> bool:
        return any(c in self.permissions for c in codes)
