from fastapi import FastAPI

from app.api.routers.health_router import router as health_router
from app.infrastructure.lifespan import lifespan


def create_app() -> FastAPI:
    """工厂函数：便于测试构造隔离实例。"""
    app = FastAPI(
        title="kb-mp API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(health_router)
    return app


app = create_app()
