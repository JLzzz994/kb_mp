"""用户领域实体与当前用户上下文。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class UserEntity:
    """纯领域实体；不含 ORM 依赖。"""

    id: int
    username: str
    display_name: str
    department_id: int
    status: int  # 1=启用 / 0=停用


@dataclass(slots=True)
class UserWithPassword(UserEntity):
    """含密码哈希，仅 Repository 内部使用。"""

    password_hash: str


@dataclass(slots=True)
class CurrentUser:
    """登录后注入到 FastAPI Depends 的当前用户信息。

    - permissions: 来自 Redis 鉴权位图（live）
    - role_codes: 用户所属角色编码（持久化 + JWT 备份）
    - dept_ids: 用户所属部门 + 所有祖先部门（鉴权时用于部门权限继承）
    - role_ids: 角色 id 列表
    - department_name: 部门名（响应填充用）
    """

    id: int
    username: str
    display_name: str
    department_id: int
    department_name: str = ""
    role_codes: list[str] = field(default_factory=list)
    dept_ids: list[int] = field(default_factory=list)
    role_ids: list[int] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)

    def has_permission(self, *codes: str) -> bool:
        return any(c in self.permissions for c in codes)


__all__ = ["UserEntity", "UserWithPassword", "CurrentUser"]
