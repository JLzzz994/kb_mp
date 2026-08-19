"""assemble_prompt 节点：构造 prompt + history trim。"""

from __future__ import annotations

from app.workflows.context import GraphContext
from app.workflows.state import ChatState

_HISTORY_MAX_TURNS = 6
_SYSTEM_PROMPT = (
    "你是 kb_mp 知识库管理平台的 AI 助手。基于提供的知识片段回答用户问题。"
    "回答末尾必须标注引用（[unit_id]）。"
)


def _trim_history(history: list[dict], max_turns: int = _HISTORY_MAX_TURNS) -> list[dict]:
    """仅保留最近 max_turns 轮对话。"""
    if len(history) <= max_turns:
        return history
    return history[-max_turns:]


async def assemble_prompt_node(state: ChatState, ctx: GraphContext) -> ChatState:
    citations = state.get("authorized_citations") or []
    history = _trim_history(state.get("history") or [])

    parts = [_SYSTEM_PROMPT, "\n# 知识片段\n"]
    for c in citations:
        parts.append(f"- [{c['unit_id']}] {c['title']}: {c['content']}\n")
    parts.append("\n# 对话历史\n")
    for turn in history:
        parts.append(f"{turn.get('role', 'user')}: {turn.get('content', '')}\n")
    parts.append(f"\n# 当前问题\n{state['question']}\n# 回答\n")

    state["prompt"] = "".join(parts)
    state["history"] = history
    return state


__all__ = ["assemble_prompt_node"]
