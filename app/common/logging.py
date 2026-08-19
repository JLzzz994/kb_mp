import sys

from loguru import logger

from app.config.settings import settings


def configure_logging() -> None:
    """统一日志格式，后续通过 loguru 上下文绑定 request_id / task_id。"""
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
    )
