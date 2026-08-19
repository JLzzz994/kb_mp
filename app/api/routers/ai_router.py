"""AI Router：会话 CRUD + 流式问答 + 续接。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUserDep, get_db, get_redis, require_permission
from app.api.schemas.chat_session_schema import (
    ChatSessionResponse,
    CreateSessionRequest,
    SessionListItem,
    UpdateSessionRequest,
)
from app.api.schemas.chat_stream_schema import (
    ChatResumeRequest,
    ChatStreamRequest,
)
from app.infrastructure.database import ChatSessionRecord
from app.infrastructure.redis_client import RedisClient
from app.services.ai_service import AIService, build_ai_service

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


def get_ai_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[RedisClient, Depends(get_redis)],
) -> AIService:
    return build_ai_service(session, redis)


AIServiceDep = Annotated[AIService, Depends(get_ai_service)]


# ── 会话 CRUD ─────────────────────────────


@router.post(
    "/sessions",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("ai:chat"))],
)
async def create_session(
    data: CreateSessionRequest,
    user: CurrentUserDep,
    db_session: Annotated[AsyncSession, Depends(get_db)],
) -> ChatSessionResponse:
    """创建会话（id 客户端生成 UUID；演示期由服务端生成）。"""
    session_id = uuid.uuid4().hex
    record = ChatSessionRecord(
        id=session_id,
        user_id=user.id,
        title=data.title,
        history_json={"turns": [], "slots": {}, "pending_turn": None},
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)
    return ChatSessionResponse(
        id=record.id,
        user_id=record.user_id,
        title=record.title,
        history_json=record.history_json,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get(
    "/sessions",
    response_model=list[SessionListItem],
    dependencies=[Depends(require_permission("ai:chat"))],
)
async def list_sessions(
    user: CurrentUserDep,
    db_session: Annotated[AsyncSession, Depends(get_db)],
) -> list[SessionListItem]:
    rows = (
        (
            await db_session.execute(
                select(ChatSessionRecord)
                .where(ChatSessionRecord.user_id == user.id)
                .order_by(ChatSessionRecord.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [SessionListItem(id=r.id, title=r.title, updated_at=r.updated_at) for r in rows]


@router.get(
    "/sessions/{session_id}",
    response_model=ChatSessionResponse,
    dependencies=[Depends(require_permission("ai:chat"))],
)
async def get_session(
    session_id: str,
    user: CurrentUserDep,
    db_session: Annotated[AsyncSession, Depends(get_db)],
) -> ChatSessionResponse:
    record = (
        await db_session.execute(
            select(ChatSessionRecord).where(
                ChatSessionRecord.id == session_id,
                ChatSessionRecord.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if record is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail={"error_code": "session_not_found"})
    return ChatSessionResponse(
        id=record.id,
        user_id=record.user_id,
        title=record.title,
        history_json=record.history_json,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.patch(
    "/sessions/{session_id}",
    response_model=ChatSessionResponse,
    dependencies=[Depends(require_permission("ai:chat"))],
)
async def update_session(
    session_id: str,
    data: UpdateSessionRequest,
    user: CurrentUserDep,
    db_session: Annotated[AsyncSession, Depends(get_db)],
) -> ChatSessionResponse:
    record = (
        await db_session.execute(
            select(ChatSessionRecord).where(
                ChatSessionRecord.id == session_id,
                ChatSessionRecord.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if record is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail={"error_code": "session_not_found"})
    if data.title is not None:
        record.title = data.title
    record.updated_at = datetime.utcnow()
    await db_session.commit()
    await db_session.refresh(record)
    return ChatSessionResponse(
        id=record.id,
        user_id=record.user_id,
        title=record.title,
        history_json=record.history_json,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("ai:chat"))],
)
async def delete_session(
    session_id: str,
    user: CurrentUserDep,
    db_session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await db_session.execute(
        delete(ChatSessionRecord).where(
            ChatSessionRecord.id == session_id,
            ChatSessionRecord.user_id == user.id,
        )
    )
    await db_session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── SSE 流式问答 ─────────────────────────────


@router.post(
    "/chat/stream",
    dependencies=[Depends(require_permission("ai:chat"))],
)
async def chat_stream(
    data: ChatStreamRequest,
    user: CurrentUserDep,
    service: AIServiceDep,
) -> Response:
    """SSE 流式问答：8 节点编排 → 8 事件流。"""
    from fastapi.responses import StreamingResponse

    async def event_generator():
        async for chunk in service.stream(
            session_id=data.session_id,
            question=data.question,
            user=user,
        ):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/chat/resume",
    dependencies=[Depends(require_permission("ai:chat"))],
)
async def chat_resume(
    data: ChatResumeRequest,
    user: CurrentUserDep,
    service: AIServiceDep,
    redis: Annotated[RedisClient, Depends(get_redis)],
) -> Response:
    """续接被 interrupt 挂起的会话：从 Redis pending 读 → 重新跑图。"""
    import json

    from fastapi.responses import StreamingResponse

    pending_raw = await redis.get(f"chat:pending:{data.session_id}")
    if not pending_raw:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail={"error_code": "no_pending_turn"})
    # pending 解析（演示期未使用具体字段；保留验证序列读成功）
    json.loads(pending_raw) if isinstance(pending_raw, str) else pending_raw

    async def event_generator():
        async for chunk in service.stream(
            session_id=data.session_id,
            question=data.question,
            user=user,
        ):
            yield chunk

    # 续接后清除 pending
    await redis.delete(f"chat:pending:{data.session_id}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
