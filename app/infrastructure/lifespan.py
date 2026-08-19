from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.common.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """应用启动/关闭钩子：初始化数据库、LLM、向量库等长生命周期客户端。"""
    configure_logging()
    # 后续接入：db_engine / llm / vector_store / file_parser_pool 等
    yield
    # 关闭清理逻辑
