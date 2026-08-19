"""应用异常体系。

> 错误码命名规范见 docs/CONTEXT.md：
> - 资源级：`{resource}_not_found`
> - 鉴权：authentication_required / invalid_access_token /
>         invalid_credentials / user_disabled
> - 业务约束：`{resource}_{constraint}`
> - 通用：`permission_denied` / `validation_failed`
"""

from __future__ import annotations


class AppError(Exception):
    """应用层基础异常，由全局 ExceptionHandler 映射为 HTTP 响应。"""

    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(self, message: str = "") -> None:
        super().__init__(message or self.error_code)
        self.message = message or self.error_code

    def to_payload(self) -> dict[str, str]:
        return {"error_code": self.error_code, "message": self.message}


class ResourceNotFoundError(AppError):
    status_code = 404
    error_code = "resource_not_found"


class AuthenticationError(AppError):
    status_code = 401
    error_code = "authentication_required"


class PermissionDeniedError(AppError):
    status_code = 403
    error_code = "permission_denied"


class ValidationError(AppError):
    status_code = 422
    error_code = "validation_failed"


# ── M1 鉴权相关 ─────────────────────────────


class InvalidCredentialsError(AuthenticationError):
    """用户名不存在或密码错误（不区分两种情况，避免账号枚举）。"""

    error_code = "invalid_credentials"


class InvalidAccessTokenError(AuthenticationError):
    """JWT 校验失败（签名错误 / 过期 / 格式错误）。"""

    error_code = "invalid_access_token"


class UserDisabledError(PermissionDeniedError):
    """账号 status=0。"""

    error_code = "user_disabled"


# ── M2 组织架构资源缺失 / 冲突 ─────────────────────────────


class UserNotFoundError(ResourceNotFoundError):
    error_code = "user_not_found"


class DepartmentNotFoundError(ResourceNotFoundError):
    error_code = "department_not_found"


class RoleNotFoundError(ResourceNotFoundError):
    error_code = "role_not_found"


class DepartmentNotEmptyError(AppError):
    """部门下仍有用户或子部门，无法删除。"""

    status_code = 422
    error_code = "department_not_empty"


class UsernameConflictError(AppError):
    """用户名唯一约束冲突。"""

    status_code = 409
    error_code = "username_conflict"
