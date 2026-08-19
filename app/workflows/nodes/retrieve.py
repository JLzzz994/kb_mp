"""retrieve 节点：从 Milvus 检索 Top-20。

> 演示期：若 Milvus 不可用，返回空 citations（继续到 rerank → 触发 interrupt）。
> 真实生产：ctx.milvus.search(query_embedding, top_k=20)。
"""

from __future__ import annotations

from app.workflows.context import GraphContext
from app.workflows.state import ChatState


async def retrieve_node(state: ChatState, ctx: GraphContext) -> ChatState:
    if ctx.milvus is None:
        # 演示期：模拟 Top-3 召回
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

    # 真实路径（Milvus 可用）
    if ctx.embedding is None:
        state["retrieved_citations"] = []
        return state
    embedding = await ctx.embedding.embed(state["question"])
    rows = await ctx.milvus.search(embedding, top_k=20)
    state["retrieved_citations"] = [
        {
            "unit_id": r["unit_id"],
            "title": r.get("title", ""),
            "score": float(r.get("score", 0.0)),
            "content": r.get("content", ""),
        }
        for r in rows
    ]
    return state


__all__ = ["retrieve_node"]
