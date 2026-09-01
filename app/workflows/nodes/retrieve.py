"""retrieve 节点：从 Milvus 检索 Top-20。

> 真实路径：ctx.embedding + ctx.milvus 可用时执行真实向量检索。
> 演示路径：向量服务不可用时返回 ERP/WMS 业务化 demo citations，便于验证完整问答链路。
> 失败降级：真实检索 IO 异常时返回空列表，由后续 interrupt 引导补充问题。
"""

from __future__ import annotations

import logging

from app.business.erp_wms import demo_citations
from app.workflows.context import GraphContext
from app.workflows.state import ChatState

logger = logging.getLogger(__name__)


async def retrieve_node(state: ChatState, ctx: GraphContext) -> ChatState:
    if ctx.embedding is None or ctx.milvus is None:
        state["retrieved_citations"] = demo_citations(state["question"])
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
        logger.error("retrieve_node.failed error=%s", exc)
        state["retrieved_citations"] = []
    return state


__all__ = ["retrieve_node"]
