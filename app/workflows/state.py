"""LangGraph ChatState TypedDict。"""

from __future__ import annotations

from typing import Any, TypedDict


class Citation(TypedDict):
    """召回的引用条目（节点间共享）。"""

    unit_id: int
    title: str
    score: float
    content: str


class ChatState(TypedDict, total=False):
    """LangGraph 图状态（M4 AI 流式 8 节点共享）。"""

    # ── 输入 ─────────────────────────────
    session_id: str
    user_id: int
    question: str
    # 用户上下文（auth_service.load_current_user 已注入）
    user_dept_ids: list[int]
    user_role_ids: list[int]
    user_permissions: list[str]

    # ── 中间态（节点写入） ─────────────────────────────
    # faq_cache_lookup
    faq_hit: dict | None  # {"answer": str, "related_unit_id": int, "unit_updated_at": str}
    # retrieve
    rewritten_query: str
    hyde_document: str
    retrieval_terms: list[str]
    retrieval_channel_counts: dict[str, int]
    retrieved_citations: list[Citation]
    # rerank
    reranked_citations: list[Citation]
    # permission_filter
    authorized_citations: list[Citation]
    unauthorized_unit_ids: list[int]
    # interrupt
    interrupt_reason: str  # "no_recall" / "no_recall_with_permission" / "low_confidence" / ""
    # assemble_prompt
    prompt: str
    history: list[dict[str, Any]]
    # generate
    answer: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    # record_log
    log_id: int
    response_time_ms: int
    source: str  # "llm" / "faq_cache"

    # ── 终止信号 ─────────────────────────────
    should_interrupt: bool  # True → 图在 interrupt_node 后挂起，不进入 assemble
    should_skip_generate: bool  # True → faq 命中后跳过 generate（直接 final）


__all__ = ["ChatState", "Citation"]
