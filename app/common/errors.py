class AppError(Exception):
    """应用层基础异常，由全局 ExceptionHandler 映射为 HTTP 响应。"""

    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(self, message: str = "") -> None:
        super().__init__(message or self.error_code)


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
