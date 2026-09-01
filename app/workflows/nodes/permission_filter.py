"""permission_filter 节点：四维 OR 鉴权过滤（复用 M3 KnowledgePermissionService）。"""

from __future__ import annotations

from app.repositories.knowledge_unit_repository import (
    KnowledgeUnitRepository,
    UnitPermissionRepository,
)
from app.services.knowledge_permission_service import (
    compute_user_permission_bitmap_sync,
)
from app.workflows.context import GraphContext
from app.workflows.state import ChatState


async def permission_filter_node(state: ChatState, ctx: GraphContext) -> ChatState:
    from app.domain.user import CurrentUser

    citations = state.get("reranked_citations") or []
    if not citations:
        state["authorized_citations"] = []
        state["unauthorized_unit_ids"] = []
        return state

    # 构造 CurrentUser（来自 state 注入的 dept_ids / role_ids）
    current_user = CurrentUser(
        id=state["user_id"],
        username="",
        display_name="",
        department_id=state["user_dept_ids"][0] if state.get("user_dept_ids") else 0,
        dept_ids=state.get("user_dept_ids", []),
        role_ids=state.get("user_role_ids", []),
        role_codes=[],
        permissions=state.get("user_permissions", []),
    )

    async with ctx.session_factory() as session:  # type: ignore[attr-defined]
        perm_repo = UnitPermissionRepository(session)
        unit_repo = KnowledgeUnitRepository(session)
        all_perms = await perm_repo.list_all()
        authorized_ids = compute_user_permission_bitmap_sync(current_user, all_perms)

        candidate_ids = sorted({int(c["unit_id"]) for c in citations})
        records = await unit_repo.list_by_ids(candidate_ids)
        active_ids = {record.id for record in records if record.status == "active"}

    active_citations = [c for c in citations if c["unit_id"] in active_ids]
    authorized = [c for c in active_citations if c["unit_id"] in authorized_ids]
    unauthorized = sorted(
        {c["unit_id"] for c in active_citations if c["unit_id"] not in authorized_ids}
    )

    state["authorized_citations"] = authorized
    state["unauthorized_unit_ids"] = unauthorized
    return state


__all__ = ["permission_filter_node"]
