"""权限码常量定义（17 码，与 docs/CONTEXT.md 锁定）。

> 备注：原 `gap:write` 已在 ADR-0007 后移除（H4 决议），不纳入枚举。
"""

from __future__ import annotations


class PermissionCode:
    """权限码常量。所有 17 码归档在 ALL_PERMISSION_CODES，供鉴权位图初始化使用。"""

    # 用户管理
    USER_READ = "user:read"
    USER_WRITE = "user:write"

    # 角色管理
    ROLE_READ = "role:read"
    ROLE_WRITE = "role:write"

    # 部门管理
    DEPT_READ = "dept:read"
    DEPT_WRITE = "dept:write"

    # 知识单元
    KNOWLEDGE_READ = "knowledge:read"
    KNOWLEDGE_WRITE = "knowledge:write"
    KNOWLEDGE_DELETE = "knowledge:delete"
    KNOWLEDGE_ASSIGN_PERMISSION = "knowledge:assign_permission"
    KNOWLEDGE_CHECK = "knowledge:check"

    # AI 问答
    AI_CHAT = "ai:chat"

    # 数据看板
    DASHBOARD_READ = "dashboard:read"

    # FAQ 管理
    FAQ_READ = "faq:read"
    FAQ_WRITE = "faq:write"
    FAQ_REVIEW = "faq:review"

    # 知识缺口
    GAP_READ = "gap:read"


ALL_PERMISSION_CODES: tuple[str, ...] = (
    PermissionCode.USER_READ,
    PermissionCode.USER_WRITE,
    PermissionCode.ROLE_READ,
    PermissionCode.ROLE_WRITE,
    PermissionCode.DEPT_READ,
    PermissionCode.DEPT_WRITE,
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
)


def assert_permission_code(code: str) -> None:
    """校验字符串是否属于 17 码之一。非法码应在上层校验拦截，不在此抛错。"""
    if code not in ALL_PERMISSION_CODES:
        raise ValueError(f"unknown permission code: {code!r}")
