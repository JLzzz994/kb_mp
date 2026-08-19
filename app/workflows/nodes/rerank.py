"""rerank 节点：动态断崖截断（score[i+1]/score[i] < 0.75 停止）。

> 演示期：直接返回所有 citations（不截断）；生产环境按 score 序列找断崖。
"""

from __future__ import annotations

from app.workflows.context import GraphContext
from app.workflows.state import ChatState

_RERANK_THRESHOLD = 0.75


async def rerank_node(state: ChatState, ctx: GraphContext) -> ChatState:
    citations = state.get("retrieved_citations") or []
    if not citations:
        state["reranked_citations"] = []
        return state

    # 按 score DESC 排序
    sorted_citations = sorted(citations, key=lambda c: c["score"], reverse=True)

    # 动态断崖：找到第一个 score[i+1] / score[i] < 0.75 的位置
    kept: list = [sorted_citations[0]]
    for i in range(1, len(sorted_citations)):
        prev = sorted_citations[i - 1]["score"]
        curr = sorted_citations[i]["score"]
        if prev == 0 or (curr / prev) < _RERANK_THRESHOLD:
            break
        kept.append(sorted_citations[i])

    state["reranked_citations"] = kept
    return state


__all__ = ["rerank_node"]
