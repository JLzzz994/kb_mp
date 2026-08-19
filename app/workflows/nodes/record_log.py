"""record_log 节点：写 qa_access_logs（失败不阻断用户）。"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from loguru import logger

from app.infrastructure.database import QaAccessLogRecord
from app.workflows.context import GraphContext
from app.workflows.state import ChatState


async def record_log_node(state: ChatState, ctx: GraphContext) -> ChatState:
    start = state.get("_start_time")
    elapsed_ms = int((time.monotonic() - start) * 1000) if start else 0
    state["response_time_ms"] = elapsed_ms

    recalled = [c["unit_id"] for c in (state.get("retrieved_citations") or [])]
    authorized = [c["unit_id"] for c in (state.get("authorized_citations") or [])]
    unauthorized = state.get("unauthorized_unit_ids") or []

    try:
        async with ctx.session_factory() as session:  # type: ignore[attr-defined]
            record = QaAccessLogRecord(
                session_id=state["session_id"],
                user_id=state["user_id"],
                question=state["question"],
                answer=state.get("answer") or (state.get("faq_hit") or {}).get("answer", ""),
                recalled_unit_ids_json=[{"id": uid, "score": 0.0} for uid in recalled],
                authorized_unit_ids_json=authorized,
                unauthorized_unit_ids_json=unauthorized,
                prompt_tokens=state.get("prompt_tokens", 0),
                completion_tokens=state.get("completion_tokens", 0),
                total_tokens=state.get("total_tokens", 0),
                response_time_ms=elapsed_ms,
                source=state.get("source") or "llm",
                related_unit_id=(state.get("authorized_citations") or [{}])[0].get("unit_id")
                if state.get("authorized_citations")
                else None,
                created_at=datetime.now(tz=UTC).replace(tzinfo=None),
            )
            session.add(record)
            await session.commit()
            state["log_id"] = record.id
    except Exception as exc:
        logger.error(
            "record_log.qa_access_log.failed session_id={} error={}", state["session_id"], exc
        )
    return state


__all__ = ["record_log_node"]
