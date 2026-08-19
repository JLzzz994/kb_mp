from fastapi import APIRouter

from app.api.schemas.health_schema import HealthResponse
from app.config.settings import settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", app_name=settings.app_name)
