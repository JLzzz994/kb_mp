"""faq_cache_lookup 节点：先查 FAQ 缓存（Redis hash + 单元版本校验）。

> 命中条件：cache 存在 + unit_updated_at 与 DB 一致。
> 命中 → state.faq_hit 设置 + should_skip_generate=True（直接 final）。
> 未命中 → 继续到 retrieve 节点。
"""

from __future__ import annotations

from app.infrastructure.database import KnowledgeUnitRecord
from app.workflows.context import GraphContext
from app.workflows.state import ChatState


async def faq_cache_lookup_node(state: ChatState, ctx: GraphContext) -> ChatState:
    if not ctx.redis:
        return state

    # 演示期：用 question_hash 作 key
    import hashlib

    from sqlalchemy import select

    qhash = hashlib.sha1(state["question"].lower().strip().encode("utf-8")).hexdigest()
    cache_key = f"faq:cache:{qhash}"

    cached = await ctx.redis.hgetall(cache_key)
    if not cached:
        return state

    related_unit_id = int(cached.get("related_unit_id", 0))
    cached_unit_updated_at = cached.get("unit_updated_at", "")

    # 校验单元版本
    if related_unit_id > 0:
        async with ctx.session_factory() as session:  # type: ignore[attr-defined]
            row = (
                await session.execute(
                    select(KnowledgeUnitRecord.updated_at).where(
                        KnowledgeUnitRecord.id == related_unit_id
                    )
                )
            ).scalar_one_or_none()
            if row is not None and row.isoformat() != cached_unit_updated_at:
                # 版本不一致 → 删除缓存
                await ctx.redis.delete(cache_key)
                return state

    state["faq_hit"] = {
        "answer": cached.get("answer", ""),
        "related_unit_id": related_unit_id,
        "unit_updated_at": cached_unit_updated_at,
    }
    state["source"] = "faq_cache"
    state["should_skip_generate"] = True
    return state


__all__ = ["faq_cache_lookup_node"]
