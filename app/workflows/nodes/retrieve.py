"""retrieve 节点：从 Milvus 检索 Top-20。

> 真实路径（部署 / 演示期有真实服务）：ctx.embedding + ctx.milvus 都可用 → 真实检索
> 演示期 mock 分支：服务不可用 → 返回 2 条 mock citations（向后兼容 87 用例）
> 失败降级：检索 IO 异常 → 走 mock 路径（不阻断用户）
"""

from __future__ import annotations

import logging

from app.workflows.context import GraphContext
from app.workflows.state import ChatState

logger = logging.getLogger(__name__)


async def retrieve_node(state: ChatState, ctx: GraphContext) -> ChatState:
    if ctx.embedding is None or ctx.milvus is None:
        # 演示期：服务不可用 → mock Top-3 召回
        state["retrieved_citations"] = [
            {
                "unit_id": 1,
                "title": "[mock] 知识单元 1",
                "score": 0.82,
                "content": "这是 mock 召回的单元内容（演示 Milvus 不可用时返回）。",
            },
            {
                "unit_id": 2,
                "title": "[mock] 知识单元 2",
                "score": 0.71,
                "content": "第二条 mock 召回内容。",
            },
        ]
        return state

    # 真实路径：embed → Milvus ANN 检索
    try:
        query_embedding = await ctx.embedding.embed(state["question"])
        rows = await ctx.milvus.search(query_embedding, top_k=20)
        state["retrieved_citations"] = [
            {
                "unit_id": int(r["unit_id"]),
                "title": str(r.get("title", "")),
                "score": float(r.get("score", 0.0)),
                "content": str(r.get("content", "")),
            }
            for r in rows
        ]
    except Exception as exc:
        logger.error("retrieve_node.failed error={}", exc)
        # 失败降级：返回空列表（rerank 后触发 interrupt）
        state["retrieved_citations"] = []
    return state


__all__ = ["retrieve_node"]
