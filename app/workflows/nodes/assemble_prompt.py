"""assemble_prompt 节点：构造 prompt + history trim。"""

from __future__ import annotations

from app.business.erp_wms import build_business_system_prompt
from app.workflows.context import GraphContext
from app.workflows.state import ChatState

_HISTORY_MAX_TURNS = 6


def _trim_history(history: list[dict], max_turns: int = _HISTORY_MAX_TURNS) -> list[dict]:
    """仅保留最近 max_turns 轮对话。"""
    if len(history) <= max_turns:
        return history
    return history[-max_turns:]


async def assemble_prompt_node(state: ChatState, ctx: GraphContext) -> ChatState:
    citations = state.get("authorized_citations") or []
    history = _trim_history(state.get("history") or [])
    system_prompt = build_business_system_prompt(state["question"])

    parts = [system_prompt, "\n\n# 已鉴权知识片段\n"]
    for c in citations:
        page_start = c.get("page_start")
        page_end = c.get("page_end")
        if page_start and page_end and page_start != page_end:
            page_label = f" p{page_start}-{page_end}"
        elif page_start:
            page_label = f" p{page_start}"
        else:
            page_label = ""
        section = c.get("section_path") or ""
        section_label = f" §{section}" if section else ""
        parts.append(
            f"- [{c['unit_id']}]{page_label}{section_label} {c['title']}: {c['content']}\n"
        )
    parts.append("\n# 对话历史\n")
    for turn in history:
        parts.append(f"{turn.get('role', 'user')}: {turn.get('content', '')}\n")
    parts.append(f"\n# 当前问题\n{state['question']}\n# 回答\n")

    state["prompt"] = "".join(parts)
    state["history"] = history
    return state


__all__ = ["assemble_prompt_node"]
