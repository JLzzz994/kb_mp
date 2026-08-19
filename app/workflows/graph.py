"""LangGraph 图编译：8 节点 + 条件路由。

> 演示期：我们不依赖 langgraph 编译（环境 + 复杂度），改为手工 async 编排。
> 真实路径：把 NodeState 替换为 StateGraph 节点，调用 .compile()。

> 流程：
> 1. faq_cache_lookup → (hit? skip_generate) → assemble_prompt? 不行直接 final
> 2. retrieve → rerank → permission_filter → interrupt?
> 3. interrupt? → record_log → final OR assemble_prompt → generate → record_log → final
"""

from __future__ import annotations

import time

from app.workflows.context import GraphContext
from app.workflows.nodes.assemble_prompt import assemble_prompt_node
from app.workflows.nodes.faq_cache_lookup import faq_cache_lookup_node
from app.workflows.nodes.generate import generate_node
from app.workflows.nodes.interrupt_node import interrupt_node
from app.workflows.nodes.permission_filter import permission_filter_node
from app.workflows.nodes.record_log import record_log_node
from app.workflows.nodes.rerank import rerank_node
from app.workflows.nodes.retrieve import retrieve_node
from app.workflows.state import ChatState


async def run_graph(state: ChatState, ctx: GraphContext) -> ChatState:
    """顺序执行 8 节点 + 条件分支。"""
    state["_start_time"] = time.monotonic()

    # 1. faq_cache_lookup
    state = await faq_cache_lookup_node(state, ctx)

    # 命中 → 跳过 retrieve/rerank/permission_filter/interrupt/assemble_prompt/generate
    if state.get("should_skip_generate"):
        state = await generate_node(state, ctx)  # 内部处理 faq 命中
        state = await record_log_node(state, ctx)
        return state

    # 2. retrieve
    state = await retrieve_node(state, ctx)
    # 3. rerank
    state = await rerank_node(state, ctx)
    # 4. permission_filter
    state = await permission_filter_node(state, ctx)
    # 5. interrupt?
    state = await interrupt_node(state, ctx)

    if state.get("should_interrupt"):
        # 中断 → 不进入 assemble/generate → 直接 record_log（记 file_interrupt status）
        state = await record_log_node(state, ctx)
        return state

    # 6. assemble_prompt
    state = await assemble_prompt_node(state, ctx)
    # 7. generate
    state = await generate_node(state, ctx)
    # 8. record_log
    state = await record_log_node(state, ctx)
    return state


__all__ = ["run_graph"]
