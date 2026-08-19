from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.dependencies import http_error_from_app_error
from app.api.routers.ai_router import router as ai_router
from app.api.routers.auth_router import router as auth_router
from app.api.routers.dashboard_router import router as dashboard_router
from app.api.routers.health_router import router as health_router
from app.api.routers.knowledge_router import router as knowledge_router
from app.api.routers.org_router import router as org_router
from app.common.errors import AppError
from app.infrastructure.lifespan import lifespan


def create_app() -> FastAPI:
    app = FastAPI(
        title="kb-mp API",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        http_exc = http_error_from_app_error(exc)
        return JSONResponse(status_code=http_exc.status_code, content=http_exc.detail)

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(org_router)
    app.include_router(knowledge_router)
    app.include_router(ai_router)
    app.include_router(dashboard_router)
    return app


app = create_app()
