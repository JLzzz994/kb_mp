"""应用启动 / 关闭钩子。

> 锁定决策（ADR-0003 / docs/CONTEXT.md Q4）：
> - 启动时 `redis_client.ping()` 失败 → `raise RuntimeError("redis unavailable")`，uvicorn 启动失败
> - 不做进程内 dict fallback（鉴权位图失效 = 越权风险）
> - pytest 环境（`PYTEST_CURRENT_TEST` 存在）跳过 ping，避免依赖 Redis
>
> M3.5 真实接入：构造 Embedding / Rerank / Milvus / LLM 工厂服务注入 app.state
> 演示期：factory 返回 None（向后兼容 87 用例 mock 路径）
> 部署：MILVUS_URL 远程 + OPENAI_API_KEY + BGE_M3_PATH 自动加载真实服务
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from app.common.logging import configure_logging
from app.infrastructure.embedding_factory import build_embedding, build_rerank
from app.infrastructure.llm_factory import build_llm, build_milvus
from app.infrastructure.redis_client import get_redis


def _is_pytest() -> bool:
    """检测是否在 pytest 中运行（避免依赖外部 Redis）。"""
    return bool(os.environ.get("PYTEST_CURRENT_TEST")) or "PYTEST_VERSION" in os.environ


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """启动 / 关闭钩子：初始化 Redis + 真实服务（演示期跳过）。"""
    configure_logging()

    redis = None
    if not _is_pytest():
        # 启动 fast-fail（ADR-0003 决策 1）
        redis = get_redis()
        await redis.ping()
        app.state.redis = redis

        # 注入真实服务（演示期 factory 返回 None → mock 路径）
        try:
            app.state.embedding = build_embedding()
            logger.info(
                "lifespan.embedding.backend={} available={}",
                getattr(app.state.embedding, "_model_path", "?"),
                app.state.embedding is not None,
            )
        except Exception as exc:
            logger.warning("lifespan.embedding.failed error={}", exc)
            app.state.embedding = None

        app.state.rerank = build_rerank()
        app.state.milvus = build_milvus()
        app.state.llm = build_llm()
    else:
        app.state.embedding = None
        app.state.rerank = None
        app.state.milvus = None
        app.state.llm = None

    try:
        yield
    finally:
        # 关闭：断开 Redis
        if not _is_pytest() and redis is not None:
            try:
                await redis.aclose()
            except Exception:  # noqa: BLE001 — 关闭阶段吞异常
                pass

        # 关闭 Milvus 连接
        if not _is_pytest() and getattr(app.state, "milvus", None) is not None:
            try:
                from pymilvus import connections

                connections.disconnect(alias="default")
            except Exception:  # noqa: BLE001
                pass
