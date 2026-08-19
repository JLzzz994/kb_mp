"""interrupt 节点：鉴权/召回为空时挂起。"""

from __future__ import annotations

import json

from app.workflows.context import GraphContext
from app.workflows.state import ChatState


async def interrupt_node(state: ChatState, ctx: GraphContext) -> ChatState:
    """触发条件（满足任一即挂起）：
    1. 召回为空（retrieved_citations == []）
    2. 召回非空但鉴权后全部被过滤（authorized_citations == []）
    3. Top-1 score < 0.2（low_confidence）
    """
    retrieved = state.get("retrieved_citations") or []
    authorized = state.get("authorized_citations") or []
    reranked = state.get("reranked_citations") or []

    reason = ""
    if not retrieved:
        reason = "no_recall"
    elif not authorized:
        reason = "no_recall_with_permission"
    elif reranked and reranked[0]["score"] < 0.2:
        reason = "low_confidence"

    if reason:
        state["interrupt_reason"] = reason
        state["should_interrupt"] = True

        # 写 pending_turn 到 Redis（resume 用）
        if ctx.redis:
            pending = {
                "session_id": state["session_id"],
                "question": state["question"],
                "reason": reason,
                "user_id": state["user_id"],
                "recalled_unit_ids": [c["unit_id"] for c in retrieved],
                "authorized_unit_ids": [c["unit_id"] for c in authorized],
            }
            await ctx.redis.set(
                f"chat:pending:{state['session_id']}",
                json.dumps(pending, default=str),
                ex=3600,
            )

    return state


__all__ = ["interrupt_node"]
