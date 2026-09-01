"""AI Service：编排 LangGraph + SSE 事件流。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.user import CurrentUser
from app.infrastructure.database import ChatSessionRecord
from app.infrastructure.redis_client import RedisClient
from app.workflows.context import GraphContext
from app.workflows.graph import run_graph
from app.workflows.state import ChatState


def _sse_event(event: str, data: dict | str) -> str:
    """格式化 SSE 事件（event: ...\ndata: ...\n\n）。"""
    if isinstance(data, dict):
        data = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {data}\n\n"


class AIService:
    def __init__(
        self,
        session: AsyncSession,
        redis: RedisClient,
        app_state: object | None = None,
    ) -> None:
        self._session = session
        self._redis = redis
        # 复用入参 session 所属的 factory（测试可注入 sql_session_factory）
        self._session_factory = lambda: session
        # 真实服务：embedding / rerank / milvus / llm（lifespan 注入到 app.state）
        self._app_state = (
            app_state
            or type("_Stub", (), {"embedding": None, "rerank": None, "milvus": None, "llm": None})()
        )

    async def _load_user_context(self, user: CurrentUser) -> dict:
        """从 user 提取 dept_ids / role_ids / permissions。"""
        # dept_ids
        from sqlalchemy import select

        from app.infrastructure.database import UserRoleRecord

        role_rows = (
            await self._session.execute(
                select(UserRoleRecord.role_id).where(UserRoleRecord.user_id == user.id)
            )
        ).all()
        role_ids = [int(r[0]) for r in role_rows]
        return {
            "dept_ids": user.dept_ids,
            "role_ids": role_ids,
            "permissions": user.permissions,
        }

    async def _save_chat_turn(
        self,
        session_id: str,
        user_id: int,
        question: str,
        answer: str,
    ) -> None:
        """追加一轮 user/assistant 到 chat_sessions.history_json。"""
        from datetime import datetime

        record = (
            await self._session.execute(
                select(ChatSessionRecord).where(ChatSessionRecord.id == session_id)
            )
        ).scalar_one_or_none()
        if record is None:
            # 新建
            record = ChatSessionRecord(
                id=session_id,
                user_id=user_id,
                title=question[:50] if question else None,
                history_json={
                    "turns": [
                        {"role": "user", "content": question},
                        {"role": "assistant", "content": answer},
                    ],
                    "slots": {},
                    "pending_turn": None,
                },
            )
            self._session.add(record)
        else:
            history = dict(record.history_json or {})
            turns = list(history.get("turns") or [])
            turns.append({"role": "user", "content": question})
            turns.append({"role": "assistant", "content": answer})
            history["turns"] = turns
            history["pending_turn"] = None
            record.history_json = history
            record.updated_at = datetime.utcnow()
        await self._session.commit()

    async def stream(
        self,
        *,
        session_id: str,
        question: str,
        user: CurrentUser,
    ) -> AsyncIterator[str]:
        """主入口：8 节点 + 8 事件流（按需发送）。"""
        ctx_data = await self._load_user_context(user)

        # 初始 state
        state: ChatState = {
            "session_id": session_id,
            "user_id": user.id,
            "question": question,
            "user_dept_ids": ctx_data["dept_ids"],
            "user_role_ids": ctx_data["role_ids"],
            "user_permissions": ctx_data["permissions"],
            "history": [],
        }

        ctx = GraphContext(
            redis=self._redis,
            session_factory=self._session_factory,
            # 从 FastAPI app.state 注入真实服务（lifespan 阶段已设置）
            embedding=getattr(self._app_state, "embedding", None),
            rerank=getattr(self._app_state, "rerank", None),
            milvus=getattr(self._app_state, "milvus", None),
            llm=getattr(self._app_state, "llm", None),
        )

        # ── ready 事件 ─────────────────────────────
        yield _sse_event("ready", {"session_id": session_id})

        # 执行图（不动 async generator 状态机；先 collect result 再 yield events）
        final_state = await run_graph(state, ctx)

        # ── 事件流：按节点输出 ─────────────────────────────
        # progress: faq_cache_lookup → retrieve → rerank → permission_filter
        for stage in ("faq_cache_lookup", "retrieve", "rerank", "permission_filter"):
            yield _sse_event("progress", {"stage": stage})

        # citation: 鉴权通过的 citations
        for c in final_state.get("authorized_citations") or []:
            yield _sse_event(
                "citation",
                {
                    "unit_id": int(c["unit_id"]),
                    "chunk_id": str(c.get("chunk_id", "")),
                    "chunk_index": int(c.get("chunk_index", 0)),
                    "title": str(c.get("title", "")),
                    "score": float(c.get("score", 0.0)),
                    "page_start": c.get("page_start"),
                    "page_end": c.get("page_end"),
                    "section_path": str(c.get("section_path", "")),
                    "source_file_name": str(c.get("source_file_name", "")),
                },
            )

        # unauthorized: 鉴权未通过的 unit_ids
        if final_state.get("unauthorized_unit_ids"):
            yield _sse_event(
                "unauthorized",
                {"unit_ids": [int(x) for x in final_state["unauthorized_unit_ids"]]},
            )

        # interrupt
        if final_state.get("should_interrupt"):
            yield _sse_event(
                "interrupt",
                {
                    "reason": final_state.get("interrupt_reason") or "low_confidence",
                    "session_id": session_id,
                },
            )
            # interrupt 也要 record_log
            await self._save_chat_turn(session_id, user.id, question, "")
            return

        # delta: 流式答案（演示期一次性 yield 整段；真实 LLM 按 chunk）
        answer = final_state.get("answer") or ""
        # 按 50 字符切分模拟流式
        for i in range(0, len(answer), 50):
            yield _sse_event("delta", {"text": answer[i : i + 50]})

        # final
        yield _sse_event(
            "final",
            {
                "answer": answer,
                "usage": {
                    "prompt_tokens": int(final_state.get("prompt_tokens") or 0),
                    "completion_tokens": int(final_state.get("completion_tokens") or 0),
                    "total_tokens": int(final_state.get("total_tokens") or 0),
                    "response_time_ms": int(final_state.get("response_time_ms") or 0),
                },
                "source": final_state.get("source") or "llm",
            },
        )

        # 持久化本轮对话
        await self._save_chat_turn(session_id, user.id, question, answer)

    def _session_factory(self):
        """复用入参 session（演示期不开启多连接）。"""
        return self._session


def build_ai_service(
    session: AsyncSession,
    redis: RedisClient,
    app_state: object | None = None,
) -> AIService:
    return AIService(session, redis, app_state=app_state)


__all__ = ["AIService", "build_ai_service"]
