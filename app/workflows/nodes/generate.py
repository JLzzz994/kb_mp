"""generate 节点：调用 LLM 流式生成答案。

> 演示期：ctx.llm 为 None 时返回 mock 答案（"这是 mock 回答…"）。
> 真实：ctx.llm.stream(prompt) → (answer, usage)。
"""

from __future__ import annotations

from app.workflows.context import GraphContext
from app.workflows.state import ChatState


async def generate_node(state: ChatState, ctx: GraphContext) -> ChatState:
    # should_skip_generate（faq 命中）已在 faq_cache_lookup 设过
    if state.get("should_skip_generate"):
        # answer 已经在 faq_hit 里
        state["answer"] = (state.get("faq_hit") or {}).get("answer", "")
        state["source"] = "faq_cache"
        return state

    if ctx.llm is None:
        # mock
        citations = state.get("authorized_citations") or []
        cite_str = " ".join(f"[{c['unit_id']}]" for c in citations)
        state["answer"] = (
            f"基于知识库检索到的 {len(citations)} 个片段，{cite_str}，"
            f"对问题「{state['question']}」的 mock 回答如下："
            f"请参考相关单元获取详细信息。"
        )
        state["prompt_tokens"] = 100
        state["completion_tokens"] = 50
        state["total_tokens"] = 150
        state["source"] = "llm"
        return state

    answer, usage = await ctx.llm.stream(state["prompt"])
    state["answer"] = answer
    state["prompt_tokens"] = int(usage.get("prompt_tokens", 0))
    state["completion_tokens"] = int(usage.get("completion_tokens", 0))
    state["total_tokens"] = int(usage.get("total_tokens", 0))
    state["source"] = "llm"
    return state


__all__ = ["generate_node"]
