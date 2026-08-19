# IMPL-M4 — AI 对话工作台（Python 方法级实现蓝图）

| 项目 | 内容 |
| --- | --- |
| 文档版本 | V1.0 |
| 阶段 | P2 |
| 编写依据 | [Spec M4](../specs/M4-AI对话工作台.md) |
| 范围 | LangGraph 8 节点 + SSE 流式输出 + 多轮会话完整方法 + pytest |

---

## 1. 文件清单

```
app/
├── api/
│   ├── routers/ai_router.py
│   └── schemas/{chat_session,chat_stream}_schema.py
├── domain/chat_session.py
├── services/ai_service.py
├── workflows/
│   ├── state.py
│   ├── context.py
│   ├── graph.py
│   └── nodes/{faq_cache_lookup,retrieve,rerank,permission_filter,interrupt_node,assemble_prompt,generate,record_log}.py
└── infrastructure/llm.py

tests/
├── test_chat_session.py
├── test_chat_stream_e2e.py
├── test_chat_interrupt_resume.py
├── test_workflow_nodes.py
└── test_chat_sse_events.py
```

---

## 2. State 与 Context

```python
# app/workflows/state.py
"""LangGraph ChatState：业务状态（可序列化部分）。"""
from typing import TypedDict


class ChatState(TypedDict, total=False):
    # === 输入 ===
    session_id: str
    user_id: int
    user_dept_ids: list[int]
    user_role_ids: list[int]
    question: str
    history: list[dict]                     # trim 后的多轮历史
    slots: dict
    pending_turn: dict | None

    # === 中间产物 ===
    faq_cached_answer: str | None
    faq_cached_unit_id: int | None
    faq_cached_unit_updated_at: str | None
    recalled_units: list[dict]              # [{unit_id, score}]
    reranked_units: list[dict]
    authorized_unit_ids: list[int]
    unauthorized_unit_ids: list[int]
    interrupt_reason: str | None
    prompt_messages: list[dict]
    answer_chunks: list[str]
    usage: dict

    # === 事件输出（供 SSE 推送）===
    events_to_emit: list[dict]              # [{type, data}]


# app/workflows/context.py
"""LangGraph ContextSchema：运行依赖（不放入状态）。"""
from typing import TypedDict


class GraphContext(TypedDict):
    llm: ChatOpenAI
    milvus: MilvusGateway
    redis: RedisClient
    permission_service: KnowledgePermissionService
    faq_cache_service: FaqCacheService
    session_repo: ChatSessionRepository
    log_repo: QaAccessLogRepository
    unit_repo: KnowledgeUnitRepository
    settings: Settings
```

---

## 3. 8 节点实现

```python
# app/workflows/nodes/faq_cache_lookup.py
"""节点节点 1：FAQ 缓存命中（含单元版本校验）。"""
from app.workflows.state import ChatState
from app.workflows.context import GraphContext


async def faq_cache_lookup(state: ChatState, ctx: GraphContext) -> dict:
    """命中即返回 + 校验知识单元版本。

    步骤：
    1. 计算 question_hash = sha1(question.lower().strip())
    2. HGETALL faq:cache:<hash>
    3. 校验 unit_updated_at 与 DB 一致
    4. 一致则返回 cached_answer；不一致则 DEL 缓存
    """
    question = state["question"]
    question_hash = __import__("hashlib").sha1(question.lower().strip().encode()).hexdigest()
    redis_key = f"faq:cache:{question_hash}"

    # 1-2. 读 Redis
    cached = await ctx["redis"].hgetall(redis_key)
    if not cached:
        return {"faq_cached_answer": None}

    # 3. 校验 unit_updated_at
    unit_id = int(cached.get("related_unit_id", 0))
    if unit_id > 0:
        db_updated_at = await ctx["unit_repo"].get_updated_at(unit_id)
        cached_updated_at = cached.get("unit_updated_at")
        if db_updated_at and db_updated_at.isoformat() != cached_updated_at:
            # 版本不一致，删除缓存
            await ctx["redis"].delete(redis_key)
            return {"faq_cached_answer": None}

    # 4. 命中
    return {
        "faq_cached_answer": cached.get("answer"),
        "faq_cached_unit_id": unit_id,
        "faq_cached_unit_updated_at": cached.get("unit_updated_at"),
    }
```

```python
# app/workflows/nodes/retrieve.py
"""节点节点 2：Milvus 向量检索。"""


async def retrieve(state: ChatState, ctx: GraphContext) -> dict:
    """检索 Top-20 候选单元。

    步骤：
    1. Milvus embedding vector search（k=20）
    2. 召回结果按 score 降序
    3. 过滤掉 status != 'active' 的
    """
    question = state["question"]

    # 1. Milvus 检索
    results = await ctx["milvus"].search(query=question, top_k=20)

    # 2-3. 转换 + 过滤
    recalled = []
    for r in results:
        # Milvus 返回 (id, score)
        unit_status = await ctx["unit_repo"].get_status(r.id)
        if unit_status != "active":
            continue
        recalled.append({"unit_id": r.id, "score": r.score})

    return {"recalled_units": recalled}
```

```python
# app/workflows/nodes/rerank.py
"""节点节点 3：动态断崖截断。"""
GAP_RATIO = 0.75
MIN_TOPK = 1
MAX_TOPK = 10


async def rerank(state: ChatState, ctx: GraphContext) -> dict:
    """动态断崖截断：score[i+1]/score[i] < GAP_RATIO 停止。

    步骤：
    1. 防御性复制 recalled_units
    2. 从头遍历：相邻比值 < GAP_RATIO 时截断
    3. 限制在 [MIN_TOPK, MAX_TOPK]
    """
    units = list(state.get("recalled_units", []))
    if not units:
        return {"reranked_units": []}

    # 1. 排序按 score desc（防御性）
    units.sort(key=lambda u: u["score"], reverse=True)

    # 2. 断崖截断
    kept = [units[0]]
    for u in units[1:MAX_TOPK]:
        prev_score = kept[-1]["score"]
        if prev_score == 0 or u["score"] / prev_score >= GAP_RATIO:
            kept.append(u)
        else:
            break

    # 3. 限制上下限
    kept = kept[:MAX_TOPK]
    if len(kept) < MIN_TOPK:
        kept = []

    return {"reranked_units": kept}
```

```python
# app/workflows/nodes/permission_filter.py
"""节点节点 4：四维鉴权（内存 OR 集合运算）。"""


async def permission_filter(state: ChatState, ctx: GraphContext) -> dict:
    """拉取所有候选 unit 的权限记录 + 内存 OR 运算。

    步骤：
    1. 收集 reranked_units 的 unit_ids
    2. 批量查 unit_permissions
    3. 构造伪 CurrentUser（仅 dept_ids + role_ids + id 字段）
    4. 调用 permission_service.compute_user_permission_bitmap_sync()
    5. 拆分 authorized / unauthorized
    6. 推 SSE unauthorized 事件
    """
    reranked = state.get("reranked_units", [])
    unit_ids = [u["unit_id"] for u in reranked]

    if not unit_ids:
        return {
            "authorized_unit_ids": [],
            "unauthorized_unit_ids": [],
            "interrupt_reason": "no_recall",
        }

    # 2. 批量查
    all_perms = await ctx["unit_repo"].list_permissions_for_units(unit_ids)

    # 3. 伪 CurrentUser
    user = SimpleNamespace(
        id=state["user_id"],
        dept_ids=state["user_dept_ids"],
        role_ids=state["user_role_ids"],
    )

    # 4. 纯函数鉴权
    authorized_set = ctx["permission_service"].compute_user_permission_bitmap_sync(
        user=user,
        unit_permissions=all_perms,
    )

    # 5. 拆分
    authorized = [uid for uid in unit_ids if uid in authorized_set]
    unauthorized = [uid for uid in unit_ids if uid not in authorized_set]

    # 6. 推 unauthorized 事件
    events = []
    if unauthorized:
        events.append({"type": "unauthorized", "data": {"unit_ids": unauthorized}})

    # 7. 推 citation 事件
    for u in reranked:
        if u["unit_id"] in authorized_set:
            title = await ctx["unit_repo"].get_title(u["unit_id"])
            events.append({
                "type": "citation",
                "data": {"unit_id": u["unit_id"], "title": title, "score": u["score"]},
            })

    return {
        "authorized_unit_ids": authorized,
        "unauthorized_unit_ids": unauthorized,
        "events_to_emit": events,
    }
```

```python
# app/workflows/nodes/interrupt_node.py
"""节点节点 5：挂起会话（鉴权/召回为空时）。"""


async def interrupt_node(state: ChatState, ctx: GraphContext) -> dict:
    """写 chat_sessions.pending_turn + 回 SSE interrupt 事件。

    步骤：
    1. 判断 reason（no_recall / no_recall_with_permission / low_confidence）
    2. 写 pending_turn 到 chat_sessions
    3. 推 SSE interrupt 事件
    """
    reason = (
        state.get("interrupt_reason")
        or ("no_recall" if not state.get("recalled_units") else "no_recall_with_permission")
    )

    # 1. 写 pending_turn
    pending_turn = {
        "question": state["question"],
        "reason": reason,
        "recalled_units": state.get("recalled_units", []),
        "authorized_unit_ids": state.get("authorized_unit_ids", []),
        "created_at": __import__("datetime").datetime.utcnow().isoformat(),
    }
    await ctx["session_repo"].set_pending_turn(
        session_id=state["session_id"],
        pending_turn=pending_turn,
    )

    # 2. 推 SSE interrupt
    return {
            "events_to_emit": [{
                "type": "interrupt",
                "data": {
                    "reason": reason,
                    "session_id": state["session_id"],
                },
            }],
        }
```

```python
# app/workflows/nodes/assemble_prompt.py
"""节点节点 6：Prompt 组装。"""
from langchain_core.messages import trim_messages

HISTORY_WINDOW = 6    # 6 轮
MAX_PROMPT_TOKENS = 8000


async def assemble_prompt(state: ChatState, ctx: GraphContext) -> dict:
    """组装 LLM 输入消息列表。

    步骤：
    1. 加载已授权 units 的正文（限 5 条避免超长）
    2. 若 state.pending_turn 存在：注入"续接上下文"提示（让 LLM 知道此前已挂起 + 当前为补充问题）
    3. 渲染 system prompt（jinja2）
    4. 截断 history 至 6 轮
    5. 拼装 messages = [system, history..., user]
    """

    # 1. 加载内容
    authorized_ids = state.get("authorized_unit_ids", [])
    units = await ctx["unit_repo"].list_content_for_ids(authorized_ids[:5])

    context_block = "\n\n".join(
        f"[知识单元 #{u.id}] {u.title}\n{u.content[:800]}"     # 单条限 800 字
        for u in units
    )

    # 2. 续接上下文（pending_turn 注入）
    resume_note = ""
    pending = state.get("pending_turn")
    if pending:
        reason = pending.get("reason", "unknown")
        original_q = pending.get("question", "")
        resume_note = (
            f"\n\n[会话续接提示] 此前用户提问「{original_q}」曾因 {reason} 被挂起，"
            f"现在用户提供了补充信息。请基于已授权知识单元直接回答当前问题，无需再次询问上下文。"
        )

    # 3. 渲染 system prompt
    sys_template = ctx["settings"].system_prompt_template    # 从 prompts/system_kb_qa.jinja2 读
    sys_msg = sys_template.render(
        context_block=context_block + resume_note,
        user_role_codes=state.get("user_role_codes", []),
    )

    # 4. history 截断（使用 trim_messages 替代手写切片）
    history = trim_messages(
        state.get("history", []),
        max_tokens=2000,
        strategy="last",
    )

    # 5. 拼装
    messages = [{"role": "system", "content": sys_msg}]
    messages.extend(history)
    messages.append({"role": "user", "content": state["question"]})

    return {"prompt_messages": messages}
```

```python
# app/workflows/nodes/generate.py
"""节点节点 7：LLM 流式生成 + Token 统计。"""


async def generate(state: ChatState, ctx: GraphContext) -> dict:
    """调用 LLM 流式输出 + 累计 Token。

    步骤：
    1. 若 FAQ 已命中，直接返回 cached_answer
    2. 否则调 ctx["llm"].astream(messages)
    3. 累积 chunks
    4. 提取 usage 元数据
    """

    # 1. FAQ 缓存命中 fast-path
    if state.get("faq_cached_answer"):
        return {
            "answer_chunks": [state["faq_cached_answer"]],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "response_time_ms": 0,
                "source": "faq_cache",
            },
            "events_to_emit": [{
                "type": "citation",
                "data": {"unit_id": state.get("faq_cached_unit_id"), "score": 1.0, "source": "faq_cache"},
            }],
        }

    # 2-3. LLM 流式
    chunks: list[str] = []
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    response_start = __import__("time").time()

    async for event in ctx["llm"].astream(state["prompt_messages"]):
        if event["type"] == "content":
            text = event["content"]
            if text:
                chunks.append(text)
                # 实时推 SSE delta
                # （由 AIService.astream 捕获 events_to_emit 统一推送）
        elif event["type"] == "usage":
            prompt_tokens = event.get("prompt_tokens", prompt_tokens)
            completion_tokens = event.get("completion_tokens", completion_tokens)
            total_tokens = event.get("total_tokens", total_tokens)

    response_time_ms = int((__import__("time").time() - response_start) * 1000)

    return {
        "answer_chunks": chunks,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "response_time_ms": response_time_ms,
            "source": "llm",
        },
    }
```

```python
# app/workflows/nodes/record_log.py
"""异步写 qa_access_logs（不阻断用户）。"""


async def record_log(state: ChatState, ctx: GraphContext) -> dict:
    """写访问日志；失败仅 warn。

    步骤：
    1. 拼装 record
    2. INSERT（失败不抛错）
    """
    try:
        await ctx["log_repo"].insert({
            "session_id": state["session_id"],
            "user_id": state["user_id"],
            "question": state["question"],
            "answer": "".join(state["answer_chunks"]),
            "recalled_unit_ids_json": __import__("json").dumps([
                {"id": u["unit_id"], "score": u["score"]}
                for u in state.get("recalled_units", [])
            ]),
            "authorized_unit_ids_json": __import__("json").dumps(state.get("authorized_unit_ids", [])),
            "unauthorized_unit_ids_json": __import__("json").dumps(state.get("unauthorized_unit_ids", [])),
            "prompt_tokens": state["usage"].get("prompt_tokens"),
            "completion_tokens": state["usage"].get("completion_tokens"),
            "total_tokens": state["usage"].get("total_tokens"),
            "response_time_ms": state["usage"].get("response_time_ms"),
            "source": state["usage"].get("source", "llm"),
        })
    except Exception as exc:
        from loguru import logger
        logger.warning("qa_access_log.write.fail session={} error={}", state["session_id"], exc)
    return {}
```

---

## 4. Graph 装配

```python
# app/workflows/graph.py
"""LangGraph 装配。"""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.workflows.state import ChatState
from app.workflows.context import GraphContext
from app.workflows.nodes import (
    faq_cache_lookup, retrieve, rerank,
    permission_filter, interrupt_node,
    assemble_prompt, generate, record_log,
)


def build_chat_graph():
    """构建 LangGraph（有 checkpointer 演示期用 MemorySaver）。

    拓扑：
    faq_cache_lookup → (hit)→ generate → record_log → END
                     → (miss)→ retrieve → rerank → permission_filter
                                              → (no authorized)→ interrupt → END
                                              → assemble_prompt → generate → record_log → END
    """
    g = StateGraph(ChatState, context_schema=GraphContext)

    # 节点
    g.add_node("faq_cache_lookup", faq_cache_lookup)
    g.add_node("retrieve", retrieve)
    g.add_node("rerank", rerank)
    g.add_node("permission_filter", permission_filter)
    g.add_node("interrupt", interrupt_node)
    g.add_node("assemble_prompt", assemble_prompt)
    g.add_node("generate", generate)
    g.add_node("record_log", record_log)

    # 入口
    g.set_entry_point("faq_cache_lookup")

    # 条件边 1：FAQ 命中
    def after_faq(state: ChatState) -> str:
        return "generate" if state.get("faq_cached_answer") else "retrieve"

    g.add_conditional_edges(
        "faq_cache_lookup",
        after_faq,
        {"generate": "generate", "retrieve": "retrieve"},
    )

    # 线性
    g.add_edge("retrieve", "rerank")
    g.add_edge("rerank", "permission_filter")

    # 条件边 2：鉴权后是否为空
    def after_perm(state: ChatState) -> str:
        return "interrupt" if not state.get("authorized_unit_ids") else "assemble_prompt"

    g.add_conditional_edges(
        "permission_filter",
        after_perm,
        {"interrupt": "interrupt", "assemble_prompt": "assemble_prompt"},
    )

    # 收尾
    g.add_edge("assemble_prompt", "generate")
    g.add_edge("generate", "record_log")
    g.add_edge("record_log", END)
    g.add_edge("interrupt", END)

    # 编译 + checkpointer
    checkpointer = MemorySaver()
    return g.compile(checkpointer=checkpointer)


# 全局单例（lifespan 启动时初始化；测试可独立构建）
_chat_graph = None


def get_chat_graph():
    global _chat_graph
    if _chat_graph is None:
        _chat_graph = build_chat_graph()
    return _chat_graph
```

---

## 5. AIService（SSE 流式编排）

```python
# app/services/ai_service.py
"""AIService：编排图执行 + SSE 事件流推送。"""
import json
from typing import AsyncIterator

from fastapi.responses import StreamingResponse
from langchain_openai import ChatOpenAI

from app.config.settings import settings


def sse_event(event_type: str, data: dict) -> bytes:
    """格式化 SSE 事件。"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


class AIService:
    def __init__(
        self,
        llm: ChatOpenAI,
        milvus: MilvusGateway,
        redis: RedisClient,
        permission_service: KnowledgePermissionService,
        faq_cache_service: FaqCacheService,
        session_repo: ChatSessionRepository,
        log_repo: QaAccessLogRepository,
        unit_repo: KnowledgeUnitRepository,
        session_service: ChatSessionService,
    ):
        self._llm = llm
        self._milvus = milvus
        self._redis = redis
        self._permission_service = permission_service
        self._faq_cache = faq_cache_service
        self._session_repo = session_repo
        self._log_repo = log_repo
        self._unit_repo = unit_repo
        self._session_service = session_service

    async def chat_stream(self, session_id: str, question: str, user: CurrentUser) -> AsyncIterator[bytes]:
        """主入口：SSE 流式问答。

        步骤：
        1. 加载 session（含 history / slots / pending_turn）
        2. 构造 initial_state
        3. 构造 graph context
        4. 调用 graph.astream(initial_state, context=ctx)
        5. 监听事件：节点输出 events_to_emit → 推 SSE
        6. 流式 LLM chunks → 推 SSE delta
        7. 收尾推 SSE final
        8. 异步更新 session（追加 turn + 清 pending_turn）
        """
        # 1. 加载 session
        session = await self._session_repo.find_by_id(session_id)
        if session is None or session.user_id != user.id:
            raise SessionNotFoundError(session_id)
        history = session.history_json.get("turns", [])
        slots = session.history_json.get("slots", {})
        pending_turn = session.history_json.get("pending_turn")

        # 2. initial state
        initial_state: ChatState = {
            "session_id": session_id,
            "user_id": user.id,
            "user_dept_ids": user.dept_ids,
            "user_role_ids": user.role_ids,
            "question": question,
            "history": history,
            "slots": slots,
            "pending_turn": pending_turn,
        }

        # 3. context
        ctx: GraphContext = {
            "llm": self._llm,
            "milvus": self._milvus,
            "redis": self._redis,
            "permission_service": self._permission_service,
            "faq_cache_service": self._faq_cache,
            "session_repo": self._session_repo,
            "log_repo": self._log_repo,
            "unit_repo": self._unit_repo,
            "settings": settings,
        }

        # 4-7. 执行图
        graph = get_chat_graph()

        # 4a. ready 事件
        yield sse_event("ready", {"session_id": session_id})

        full_answer = ""
        usage = {}
        interrupt_event = None

        # 5. astream with stream_mode=events
        async for event in graph.astream(
            initial_state,
            config={"configurable": {"thread_id": session_id}},
            context=ctx,
            stream_mode="events",
        ):
            kind = event["event"]
            data = event.get("data", {})

            if kind == "on_chain_start":
                # 节点开始 - 可推 progress
                node_name = event.get("name", "")
                if node_name and node_name != "__start__":
                    yield sse_event("progress", {"step": node_name})

            elif kind == "on_chain_end":
                # 节点结束 - 推 events_to_emit
                output = data.get("output", {})
                if isinstance(output, dict) and "events_to_emit" in output:
                    for e in output["events_to_emit"]:
                        yield sse_event(e["type"], e["data"])
                        if e["type"] == "interrupt":
                            interrupt_event = e
                if "answer_chunks" in output:
                    full_answer = "".join(output["answer_chunks"])
                if "usage" in output:
                    usage = output["usage"]

            elif kind == "on_chat_model_stream":
                # 流式 LLM chunk
                chunk = data.get("chunk", {})
                content = chunk.get("content", "")
                if content:
                    yield sse_event("delta", {"text": content})

        # 7. final 事件
        if not interrupt_event:
            yield sse_event("final", {"answer": full_answer, "usage": usage})

        # 8. 异步更新 session（通过 ChatSessionService 注入）
        await self._update_session(
            session_id=session_id,
            current_user=user,
            question=question,
            answer=full_answer,
            citations=usage.get("source") == "llm",
            interrupt=interrupt_event,
        )

    async def _update_session(
        self,
        session_id: str,
        current_user: CurrentUser,
        question: str,
        answer: str,
        citations: bool,
        interrupt: dict | None,
    ):
        """追加 turn + 清 pending_turn（经 ChatSessionService）。"""
        from datetime import datetime
        new_turn = {
            "role": "user",
            "content": question,
            "created_at": datetime.utcnow().isoformat(),
        }
        if answer:
            new_turn_answer = {
                "role": "assistant",
                "content": answer,
                "created_at": datetime.utcnow().isoformat(),
            }
        else:
            new_turn_answer = None
        await self._session_service.append_turn(
            session_id=session_id,
            user=current_user,
            user_turn=new_turn,
            assistant_turn=new_turn_answer,
        )

    async def chat_resume(self, session_id: str, question: str, user: CurrentUser) -> AsyncIterator[bytes]:
        """续接被 interrupt 挂起的会话。

        步骤：
        1. 加载 session，校验归属
        2. 读取 pending_turn；若不存在 → fallback 到 chat_stream
        3. 构造 initial_state 时携带 pending_turn（让 assemble_prompt 感知）
        4. 复用 chat_stream 但传入含 pending_turn 的 initial_state
        """
        session = await self._session_repo.find_by_id(session_id)
        if session is None or session.user_id != user.id:
            raise SessionNotFoundError(session_id)

        pending = session.history_json.get("pending_turn") if session.history_json else None
        if pending is None:
            # 非挂起状态，直接走 chat_stream
            async for chunk in self.chat_stream(session_id, question, user):
                yield chunk
            return

        # 复用 chat_stream 逻辑（chat_stream 内部会读 pending_turn 到 initial_state，
        # 此处不需重复注入；保留显式判断以满足 Spec M4 §7.2 "服务端自动检测 pending_turn 续接" 的语义）。
        # pending_turn 会被 chat_stream 自动装载到 initial_state.pending_turn；
        # 同时 assemble_prompt 会基于 pending_turn 调整上下文（例如携带 recall 历史与 reason）。
        logger.info(
            "ai.chat_resume session={} user={} reason={}",
            session_id, user.id, pending.get("reason"),
        )
        async for chunk in self.chat_stream(session_id, question, user):
            yield chunk
```

---

## 6. ChatSessionService

```python
# app/repositories/chat_session_repository.py
class ChatSessionRepository:
    async def find_by_id(self, session_id: str) -> ChatSessionRecord | None: ...
    async def list_by_user(self, user_id: int, *, page: int, page_size: int) -> tuple[list[ChatSessionRecord], int]: ...
    async def insert(self, record: ChatSessionRecord) -> None: ...
    async def delete(self, session_id: str, user_id: int) -> None: ...

    async def append_turn_and_clear_pending(
        self, session_id: str, user_turn: dict, assistant_turn: dict | None,
    ) -> None:
        """追加 turn + 清 pending_turn。

        SQL（MySQL JSON）:
        UPDATE chat_sessions
        SET history_json = JSON_SET(
            history_json,
            '$.turns', JSON_ARRAY_APPEND(history_json->'$.turns', '$', ?),
            ...
        ),
        updated_at = NOW()
        WHERE id = ?
        """
        # 用 JSON_SET 原子更新
        ...

    async def set_pending_turn(self, session_id: str, pending_turn: dict) -> None:
        """写 pending_turn。"""
        ...


# app/services/chat_session_service.py
class ChatSessionService:
    def __init__(self, repo: ChatSessionRepository):
        self._repo = repo

    async def create(self, user: CurrentUser, req: CreateSessionRequest) -> ChatSessionResponse:
        session_id = str(uuid.uuid4())
        await self._repo.insert(ChatSessionRecord(
            id=session_id,
            user_id=user.id,
            title=req.title or "新会话",
            history_json={"turns": [], "slots": {}, "pending_turn": None},
        ))
        return await self.get(session_id, user)

    async def get(self, session_id: str, user: CurrentUser) -> ChatSessionResponse:
        record = await self._repo.find_by_id(session_id)
        if record is None:
            raise SessionNotFoundError(session_id)
        if record.user_id != user.id:
            raise SessionPermissionDeniedError()
        return ChatSessionResponse(
            id=record.id,
            title=record.title,
            history_json=record.history_json,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    async def list(
        self,
        user: CurrentUser,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[SessionListItem], int]:
        """当前用户会话列表（按 updated_at DESC）。

        步骤：
        1. 调 repo.list_by_user
        2. 转 SessionListItem
        """
        rows, total = await self._repo.list_by_user(
            user_id=user.id, page=page, page_size=page_size,
        )
        items = [
            SessionListItem(
                id=row.id,
                title=row.title,
                updated_at=row.updated_at,
            )
            for row in rows
        ]
        return items, total

    async def update(self, session_id: str, req: UpdateSessionRequest, user: CurrentUser) -> ChatSessionResponse:
        record = await self._repo.find_by_id(session_id)
        if record is None or record.user_id != user.id:
            raise SessionNotFoundError(session_id)
        if req.title is not None:
            record.title = req.title
            await self._session.flush()
        return await self.get(session_id, user)

    async def delete(self, session_id: str, user: CurrentUser) -> None:
        record = await self._repo.find_by_id(session_id)
        if record is None or record.user_id != user.id:
            raise SessionNotFoundError(session_id)
        await self._repo.delete(session_id, user.id)

    async def append_turn(
        self,
        session_id: str,
        user: CurrentUser,
        user_turn: dict,
        assistant_turn: dict | None,
    ) -> None:
        """追加 user + assistant 一对 turn + 清 pending_turn。

        步骤：
        1. 校验 session 存在 + 归属当前用户
        2. 调 repo.append_turn_and_clear_pending
        """
        session = await self._repo.find_by_id(session_id)
        if session is None or session.user_id != user.id:
            raise SessionNotFoundError(session_id)
        await self._repo.append_turn_and_clear_pending(
            session_id=session_id,
            user_turn=user_turn,
            assistant_turn=assistant_turn,
        )
```

---

## 7. Router

```python
# app/api/routers/ai_router.py
router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


@router.post("/sessions", response_model=ChatSessionResponse, status_code=201,
             dependencies=[Depends(require_permission("ai:chat"))])
async def create_session(req: CreateSessionRequest, user: CurrentUserDep, service: ChatSessionServiceDep):
    return await service.create(user, req)


@router.get("/sessions", response_model=SessionListResponse,
            dependencies=[Depends(require_permission("ai:chat"))])
async def list_sessions(user: CurrentUserDep, service: ChatSessionServiceDep,
                        page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    items, total = await service.list(user, page, page_size)
    return SessionListResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/sessions/{session_id}", response_model=ChatSessionResponse,
            dependencies=[Depends(require_permission("ai:chat"))])
async def get_session(session_id: str, user: CurrentUserDep, service: ChatSessionServiceDep):
    return await service.get(session_id, user)


@router.patch("/sessions/{session_id}", response_model=ChatSessionResponse,
              dependencies=[Depends(require_permission("ai:chat"))])
async def update_session(session_id: str, req: UpdateSessionRequest, user: CurrentUserDep, service: ChatSessionServiceDep):
    return await service.update(session_id, req, user)


@router.delete("/sessions/{session_id}", status_code=204,
               dependencies=[Depends(require_permission("ai:chat"))])
async def delete_session(session_id: str, user: CurrentUserDep, service: ChatSessionServiceDep):
    await service.delete(session_id, user)


@router.post("/chat/stream",
             dependencies=[Depends(require_permission("ai:chat"))])
async def chat_stream(
    req: ChatStreamRequest,
    user: CurrentUserDep,
    service: AIServiceDep,
):
    """SSE 流式���答。"""
    return StreamingResponse(
        service.chat_stream(req.session_id, req.question, user),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",       # 关闭 Nginx 缓冲
        },
    )


@router.post("/chat/resume",
             dependencies=[Depends(require_permission("ai:chat"))])
async def chat_resume(
    req: ChatResumeRequest,
    user: CurrentUserDep,
    service: AIServiceDep,
):
    """SSE 续接被 interrupt 挂起的会话。"""
    return StreamingResponse(
        service.chat_resume(req.session_id, req.question, user),
        media_type="text/event-stream",
    )
```

---

## 8. 测试用例

```python
# tests/test_chat_session.py
@pytest.mark.asyncio
class TestSession:

    async def test_create_session_returns_uuid(self, async_client, alice_token):
        resp = await async_client.post(
            "/api/v1/ai/sessions",
            json={"title": "测试会话"},
            headers=auth_header(alice_token),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert len(body["id"]) == 36      # UUID4
        assert body["title"] == "测试会话"

    async def test_get_session_other_user_returns_403(self, async_client, alice_token, bob_token):
        # Alice 创建
        create_resp = await async_client.post("/api/v1/ai/sessions", json={}, headers=auth_header(alice_token))
        session_id = create_resp.json()["id"]
        # Bob 访问
        resp = await async_client.get(f"/api/v1/ai/sessions/{session_id}", headers=auth_header(bob_token))
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "chat_session_not_owned"


# tests/test_chat_stream_e2e.py
@pytest.mark.asyncio
class TestChatStream:

    async def test_full_pipeline_emits_events(
        self, async_client, alice_token, seeded_units_with_global_perm, mock_llm_with_text,
    ):
        req = {"session_id": str(uuid.uuid4()), "question": "如何重置密码？"}
        resp = await async_client.post(
            "/api/v1/ai/chat/stream",
            json=req,
            headers=auth_header(alice_token),
        )
        assert resp.status_code == 200
        # 解析 SSE 流
        events = parse_sse_events(resp.text)
        types = [e["type"] for e in events]
        assert "ready" in types
        assert "delta" in types
        assert "final" in types
        final = next(e for e in events if e["type"] == "final")
        assert "answer" in final["data"]
        assert "usage" in final["data"]

    async def test_faq_cache_hit_skips_retrieve(
        self, async_client, alice_token, seeded_faq_cache,
    ):
        req = {"session_id": str(uuid.uuid4()), "question": "重置密码"}
        resp = await async_client.post(
            "/api/v1/ai/chat/stream",
            json=req,
            headers=auth_header(alice_token),
        )
        events = parse_sse_events(resp.text)
        types = [e["type"] for e in events]
        # 应跳过 retrieve，无 progress 节点
        assert "progress" not in types or "retrieve" not in [e["data"].get("step") for e in events if e["type"] == "progress"]
        final = next(e for e in events if e["type"] == "final")
        assert final["data"]["usage"]["source"] == "faq_cache"

    async def test_unauthorized_units_emitted(
        self, async_client, alice_token, seeded_units_mixed_perm,
    ):
        req = {"session_id": str(uuid.uuid4()), "question": "敏感问题"}
        resp = await async_client.post(
            "/api/v1/ai/chat/stream",
            json=req,
            headers=auth_header(alice_token),
        )
        events = parse_sse_events(resp.text)
        unauthorized = [e for e in events if e["type"] == "unauthorized"]
        assert len(unauthorized) >= 1


# tests/test_chat_interrupt_resume.py
@pytest.mark.asyncio
class TestInterrupt:

    async def test_interrupt_when_no_recall(
        self, async_client, alice_token, mock_llm_no_recall,
    ):
        req = {"session_id": str(uuid.uuid4()), "question": "完全没收录的问题"}
        resp = await async_client.post(
            "/api/v1/ai/chat/stream",
            json=req,
            headers=auth_header(alice_token),
        )
        events = parse_sse_events(resp.text)
        interrupt = [e for e in events if e["type"] == "interrupt"]
        assert len(interrupt) == 1
        assert interrupt[0]["data"]["reason"] == "no_recall"

    async def test_interrupt_writes_pending_turn(self, async_client, alice_token, mock_llm_no_recall):
        session_id = str(uuid.uuid4())
        # 制造 interrupt
        await async_client.post(
            "/api/v1/ai/chat/stream",
            json={"session_id": session_id, "question": "x"},
            headers=auth_header(alice_token),
        )
        # 验证 pending_turn 写入
        get_resp = await async_client.get(
            f"/api/v1/ai/sessions/{session_id}",
            headers=auth_header(alice_token),
        )
        body = get_resp.json()
        assert body["history_json"]["pending_turn"] is not None

    async def test_resume_uses_pending_turn(
        self, async_client, alice_token, mock_llm,
    ):
        session_id = str(uuid.uuid4())
        # 制造 interrupt
        await async_client.post(
            "/api/v1/ai/chat/stream",
            json={"session_id": session_id, "question": "x"},
            headers=auth_header(alice_token),
        )
        # 续接
        resp = await async_client.post(
            "/api/v1/ai/chat/resume",
            json={"session_id": session_id, "question": "补充信息"},
            headers=auth_header(alice_token),
        )
        events = parse_sse_events(resp.text)
        # 应正常产出 final（pending_turn 自动清除）
        assert "final" in [e["type"] for e in events]


# tests/test_workflow_nodes.py
@pytest.mark.asyncio
class TestNodes:

    async def test_rerank_dynamic_cut(self):
        from app.workflows.nodes.rerank import rerank, GAP_RATIO, MAX_TOPK
        # 构造：scores = [1.0, 0.9, 0.7, 0.3]
        # 0.9/1.0 = 0.9 > 0.75 → 保留
        # 0.7/0.9 = 0.78 > 0.75 → 保留
        # 0.3/0.7 = 0.43 < 0.75 → 截断
        state = {"recalled_units": [
            {"unit_id": 1, "score": 1.0},
            {"unit_id": 2, "score": 0.9},
            {"unit_id": 3, "score": 0.7},
            {"unit_id": 4, "score": 0.3},
        ]}
        result = await rerank(state, mock_ctx({}))
        assert [u["unit_id"] for u in result["reranked_units"]] == [1, 2, 3]

    async def test_faq_cache_lookup_version_mismatch_invalidates(
        self, redis_client, mock_unit_repo,
    ):
        # 设置缓存
        await redis_client.hset("faq:cache:abc", mapping={
            "answer": "old answer",
            "related_unit_id": "1",
            "unit_updated_at": "2026-01-01T00:00:00",
        })
        # mock unit_repo 返回不同 updated_at
        mock_unit_repo.get_updated_at.return_value = datetime(2026, 8, 19)
        state = {"question": "test"}
        result = await faq_cache_lookup(state, mock_ctx({
            "redis": redis_client,
            "unit_repo": mock_unit_repo,
        }))
        assert result["faq_cached_answer"] is None
        # 缓存应被删除
        assert await redis_client.exists("faq:cache:abc") == 0
```

---

## 9. 验收 Checklist

- [ ] 8 节点编排完整工作
- [ ] SSE 8 种事件类型（ready/progress/delta/citation/unauthorized/interrupt/final/error）正确产出
- [ ] FAQ 缓存命中跳过 retrieve + permission_filter
- [ ] 鉴权后空集触发 interrupt
- [ ] interrupt 写 chat_sessions.pending_turn
- [ ] resume 接口消费 pending_turn
- [ ] 流式 P95 < 3s（演示数据）
- [ ] 单元测试覆盖 7 个节点 + AIService