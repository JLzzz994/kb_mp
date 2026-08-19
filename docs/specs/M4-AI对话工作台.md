# Spec M4 — AI 对话工作台

| 项目 | 内容 |
| --- | --- |
| 文档版本 | V1.0 |
| 阶段 | P2 |
| 依赖模块 | M1（鉴权）/ M3（鉴权接口 / 知识单元 / Redis 位图） |
| 下游模块 | M5（看板数据源）/ M6（FAQ 缓存命中 + 缺口识别） |

---

## 1. 范围与依据

**范围**：多轮会话管理、LangGraph 8 节点 AI 鉴权问答、SSE 流式输出、interrupt/resume 续接、FAQ 缓存命中。

**依据**：
- 《PRD》§2.9.3 AI 对话鉴权工作台、§2.9.4 AI 问答鉴权规则
- 《概要设计》§5.2 AI 鉴权问答流程（8 节点：faq_cache_lookup → retrieve → rerank → permission_filter → interrupt? → assemble_prompt → generate → record_log）
- 《数据对象》§4.1 qa_access_logs、§4.2 chat_sessions（含 slots / pending_turn）
- 《接口约定》§6 SSE（事件类型 `ready / progress / delta / citation / unauthorized / interrupt / final / error`）+ §7.4 AI 对话
- 《原型设计》§8.5 AI 对话鉴权工作台

**非目标**：
- 多模态输入（图片、语音）—— 演示期仅文本
- Agent 工具调用（Function Calling / MCP）
- 模型微调 / RLHF

---

## 2. 模块概览

```
[POST /api/v1/ai/chat/stream]
   │
   ▼
AIService.chat_stream(request, user)
   │
   ▼
LangGraph Runtime ──▶ 8 节点编排
   │
   ├─ faq_cache_lookup    → Redis hash（含单元版本校验）
   ├─ retrieve            → MilvusGateway.search（Top-20）
   ├─ rerank              → 动态断崖截断（score[i+1]/score[i] < 0.75 停止）
   ├─ permission_filter   → M3 KnowledgePermissionService.compute_user_permission_bitmap_sync()
   ├─ interrupt (条件)    → 写 chat_sessions.pending_turn + 回 SSE interrupt 事件
   ├─ assemble_prompt     → LangChain PromptTemplate + history（≤6 轮，trim_messages）
   ├─ generate            → ChatOpenAI.stream()
   └─ record_log          → qa_access_logs INSERT（失败不抛错）

异步：
APScheduler: faq_mining_service（每日 02:00）—— 见 M6
chat_sessions 状态变更触发 Redis 缓存清理（无）
```

---

## 3. 目录与文件清单

### 3.1 新增

```
app/
├── api/
│   ├── routers/
│   │   └── ai_router.py              # /sessions /chat/stream /chat/resume
│   └── schemas/
│       ├── chat_session_schema.py    # CreateSession / UpdateSession
│       └── chat_stream_schema.py     # StreamRequest / CitationEvent / UnauthorizedEvent / InterruptEvent
├── domain/
│   └── chat_session.py               # ChatSessionEntity / SlotState / PendingTurn
├── services/
│   └── ai_service.py                 # AIService（编排图执行 + 事件流）
├── workflows/
│   ├── state.py                      # ChatState TypedDict
│   ├── context.py                    # GraphContext（LLM / Milvus / Redis / Repos）
│   ├── graph.py                      # add_node / add_edge / compile
│   └── nodes/
│       ├── faq_cache_lookup.py
│       ├── retrieve.py
│       ├── rerank.py
│       ├── permission_filter.py
│       ├── interrupt_node.py          # 鉴权/召回为空时挂起
│       ├── assemble_prompt.py
│       ├── generate.py
│       └── record_log.py
├── infrastructure/
│   └── llm.py                        # ChatOpenAI async client（OpenAI-compatible base_url）
└── prompts/
    ├── system_kb_qa.jinja2
    └── rerank_decision.jinja2        # 备用（如未来引入 LLM 重排）

tests/
├── test_chat_session.py
├── test_chat_stream_e2e.py
├── test_chat_interrupt_resume.py
├── test_workflow_nodes.py
└── test_chat_sse_events.py
```

### 3.2 修改
- `app/api/app.py` — 注册 `ai_router`；注册 SSE 异常 handler
- `app/infrastructure/lifespan.py` — 启动 LLM client
- `app/config/settings.py` — 增 `openai_api_key` / `openai_base_url` / `openai_model` / `embedding_model`
- M6 `gap_detector` —— **M4 `record_log` 节点 → M6 `GapDetector`**：record_log 写完 qa_access_logs 后，触发 GapDetector 按 Top-1 < 0.5 且 Top-3 均 < 0.55 的阈值识别知识缺口（写入 `knowledge_gaps` 表）

---

## 4. 数据对象与迁移

### 4.1 关键字段（详见《数据对象 §4》）

| 表 | 关键字段 |
| --- | --- |
| chat_sessions | `id (UUID) / user_id / title / history_json {turns,slots,pending_turn}` |
| qa_access_logs | `session_id / user_id / question / answer / recalled_unit_ids_json / authorized_unit_ids_json / unauthorized_unit_ids_json / prompt_tokens / completion_tokens / total_tokens / response_time_ms / source` |

### 4.2 关键 Pydantic Schema

```python
# chat_session_schema.py
class CreateSessionRequest(BaseModel):
    title: str | None = None


class UpdateSessionRequest(BaseModel):
    title: str | None = None


class ChatSessionResponse(BaseModel):
    id: str
    title: str | None
    history_json: dict  # {turns: [...], slots: {...}, pending_turn: ...}
    created_at: datetime
    updated_at: datetime


class SessionListItem(BaseModel):
    id: str
    title: str | None
    updated_at: datetime


# chat_stream_schema.py
class ChatStreamRequest(BaseModel):
    session_id: str
    question: str = Field(min_length=1, max_length=2000)


class ChatResumeRequest(BaseModel):
    session_id: str
    question: str = Field(min_length=1, max_length=2000)


# SSE Event 数据结构（在 api 层定义 EventSourceResponse data payload）
class CitationEvent(BaseModel):
    unit_id: int
    title: str
    score: float


class UnauthorizedEvent(BaseModel):
    unit_ids: list[int]


class InterruptEvent(BaseModel):
    reason: Literal["no_recall", "no_recall_with_permission", "low_confidence"]
    session_id: str


class FinalEvent(BaseModel):
    answer: str
    usage: dict  # {prompt_tokens, completion_tokens, total_tokens, response_time_ms}
```

---

## 5. 后端设计

### 5.1 路由

**路由前缀**：所有端点统一 `/api/v1/<domain>` 前缀，详见接口约定文档 §7 各模块接口分组清单。

| Method | 完整路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| POST | `/api/v1/ai/sessions` | `ai:chat` | 创建会话（id 客户端生成 UUID） |
| GET | `/api/v1/ai/sessions` | `ai:chat` | 当前用户会话列表（按 updated_at DESC） |
| GET | `/api/v1/ai/sessions/{id}` | `ai:chat` | 会话详情 |
| PATCH | `/api/v1/ai/sessions/{id}` | `ai:chat` | 更新标题 |
| DELETE | `/api/v1/ai/sessions/{id}` | `ai:chat` | 删除会话 |
| POST | `/api/v1/ai/chat/stream` | `ai:chat` | **SSE 流式问答** |
| POST | `/api/v1/ai/chat/resume` | `ai:chat` | 续接被 `interrupt` 挂起的会话 |

### 5.2 LangGraph State（`workflows/state.py`）

```python
class ChatState(TypedDict, total=False):
    # 输入
    session_id: str
    user_id: int
    user_dept_ids: list[int]
    user_role_ids: list[int]
    question: str
    history: list[dict]  # trim 后的多轮历史
    slots: dict
    pending_turn: dict | None

    # 中间产物
    faq_cached_answer: str | None
    faq_cached_unit_id: int | None
    faq_cached_unit_updated_at: datetime | None
    recalled_units: list[dict]  # [{unit_id, score}]
    reranked_units: list[dict]
    authorized_unit_ids: list[int]
    unauthorized_unit_ids: list[int]
    interrupt_reason: str | None
    prompt_messages: list[dict]
    answer_chunks: list[str]
    usage: dict  # {prompt_tokens, completion_tokens, total_tokens, response_time_ms}

    # 输出（供 SSE 推送）
    events_to_emit: list[dict]  # [{type: ..., data: ...}, ...]
```

### 5.3 GraphContext（`workflows/context.py`）

```python
class GraphContext(TypedDict):
    llm: ChatOpenAI  # 主 LLM
    milvus: MilvusGateway  # 向量检索
    redis: RedisClient  # FAQ 缓存 / 鉴权位图
    permission_service: KnowledgePermissionService  # M3
    faq_cache_repo: FaqCacheRepository  # M6 接口
    session_repo: ChatSessionRepository
    log_repo: QaAccessLogRepository
    unit_repo: KnowledgeUnitRepository  # 用于 FAQ 版本校验
    settings: Settings
```

### 5.4 Graph（`workflows/graph.py`）

```python
def build_chat_graph() -> CompiledGraph:
    g = StateGraph(ChatState, context_schema=GraphContext)
    g.add_node("faq_cache_lookup", faq_cache_lookup)
    g.add_node("retrieve", retrieve)
    g.add_node("rerank", rerank)
    g.add_node("permission_filter", permission_filter)
    g.add_node("interrupt", interrupt_node)
    g.add_node("assemble_prompt", assemble_prompt)
    g.add_node("generate", generate)
    g.add_node("record_log", record_log)

    g.set_entry_point("faq_cache_lookup")

    g.add_conditional_edges(
        "faq_cache_lookup",
        lambda s: "generate" if s.get("faq_cached_answer") else "retrieve",
        {"generate": "generate", "retrieve": "retrieve"},
    )

    g.add_edge("retrieve", "rerank")
    g.add_edge("rerank", "permission_filter")

    g.add_conditional_edges(
        "permission_filter",
        lambda s: "interrupt" if not s.get("authorized_unit_ids") else "assemble_prompt",
        {"interrupt": "interrupt", "assemble_prompt": "assemble_prompt"},
    )

    g.add_edge("assemble_prompt", "generate")
    g.add_edge("generate", "record_log")
    g.add_edge("record_log", END)
    g.add_edge("interrupt", END)  # 不写 record_log

    return g.compile()
```

### 5.5 节点签名

```python
# workflows/nodes/faq_cache_lookup.py
async def faq_cache_lookup(state: ChatState, ctx: GraphContext) -> dict:
    """命中即返回 + 校验知识单元版本"""
    h = sha1(state["question"].lower().strip()).hexdigest()
    cached = await ctx["redis"].hgetall(f"faq:cache:{h}")
    if not cached:
        return {"faq_cached_answer": None}
    unit_updated = await ctx["unit_repo"].get_updated_at(int(cached["related_unit_id"]))
    if unit_updated and unit_updated.isoformat() == cached.get("unit_updated_at"):
        return {"faq_cached_answer": cached["answer"], "faq_cached_unit_id": int(cached["related_unit_id"])}
    await ctx["redis"].delete(f"faq:cache:{h}")
    return {"faq_cached_answer": None}

# workflows/nodes/retrieve.py
async def retrieve(state: ChatState, ctx: GraphContext) -> dict:
    """Milvus Top-20 向量检索"""
    results = await ctx["milvus"].search(state["question"], top_k=20)
    return {"recalled_units": [{"unit_id": r.id, "score": r.score} for r in results]}

# workflows/nodes/rerank.py
GAP_RATIO = 0.75          # score[i+1]/score[i] < 0.75 停止
MIN_TOPK = 1
MAX_TOPK = 10
async def rerank(state: ChatState, ctx: GraphContext) -> dict:
    """动态断崖截断"""
    units = state["recalled_units"]
    if not units:
        return {"reranked_units": []}
    kept = [units[0]]
    for u in units[1:MAX_TOPK]:
        if kept[-1]["score"] == 0 or u["score"] / kept[-1]["score"] >= GAP_RATIO:
            kept.append(u)
        else:
            break
    return {"reranked_units": kept[:MAX_TOPK]}

# workflows/nodes/permission_filter.py
async def permission_filter(state: ChatState, ctx: GraphContext) -> dict:
    """拉取所有相关 unit 的权限记录（一次性）+ 内存 OR 集合运算"""
    unit_ids = [u["unit_id"] for u in state["reranked_units"]]
    if not unit_ids:
        return {"authorized_unit_ids": [], "unauthorized_unit_ids": []}
    all_permissions = await ctx["unit_repo"].list_permissions_for_units(unit_ids)
    user = CurrentUser(
        id=state["user_id"], dept_ids=state["user_dept_ids"], role_ids=state["user_role_ids"]
    )
    bitmap = ctx["permission_service"].compute_user_permission_bitmap_sync(user, all_permissions)
    authorized = [uid for uid in unit_ids if uid in bitmap]
    unauthorized = [uid for uid in unit_ids if uid not in bitmap]
    return {"authorized_unit_ids": authorized, "unauthorized_unit_ids": unauthorized}

# workflows/nodes/interrupt_node.py
async def interrupt_node(state: ChatState, ctx: GraphContext) -> dict:
    """挂起会话：写 pending_turn + 回 SSE interrupt 事件"""
    reason = state.get("interrupt_reason") or (
        "no_recall" if not state.get("recalled_units") else "no_recall_with_permission"
    )
    await ctx["session_repo"].set_pending_turn(
        session_id=state["session_id"],
        pending_turn={
            "question": state["question"],
            "reason": reason,
            "recalled_units": state.get("recalled_units", []),
            "created_at": datetime.utcnow().isoformat(),
        },
    )
    return {"events_to_emit": [{"type": "interrupt", "data": {"reason": reason, "session_id": state["session_id"]}}]}

# workflows/nodes/assemble_prompt.py
HISTORY_WINDOW = 6
async def assemble_prompt(state: ChatState, ctx: GraphContext) -> dict:
    """Prompt 组装：系统提示 + 历史（≤6 轮，trim_messages）+ 引用上下文"""
    sys_msg = render_system_prompt(ctx["settings"])  # from prompts/system_kb_qa.jinja2
    authorized_docs = await ctx["unit_repo"].list_content_for_ids(state["authorized_unit_ids"])
    context_block = "\n\n".join(
        f"[知识单元 {d.id}] {d.title}\n{d.content}" for d in authorized_docs
    )
    history = trim_messages(state["history"], max_messages=HISTORY_WINDOW * 2)
    messages = [{"role": "system", "content": sys_msg.format(context=context_block, history=history)}]
    messages.extend(history)
    messages.append({"role": "user", "content": state["question"]})
    return {"prompt_messages": messages}

# workflows/nodes/generate.py
async def generate(state: ChatState, ctx: GraphContext) -> dict:
    """LLM 流式输出 + Token 统计"""
    if state.get("faq_cached_answer"):
        return {"answer_chunks": [state["faq_cached_answer"]], "usage": {"source": "faq_cache", ...}}
    chunks: list[str] = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    async for event in ctx["llm"].astream(state["prompt_messages"]):
        if event.type == "content":
            chunks.append(event.content)
            # 推送 SSE delta（由 AIService 监听事件总线）
        elif event.type == "usage":
            usage = {"prompt_tokens": event.prompt_tokens, "completion_tokens": event.completion_tokens, "total_tokens": event.total_tokens}
    return {"answer_chunks": chunks, "usage": usage}

# workflows/nodes/record_log.py
async def record_log(state: ChatState, ctx: GraphContext) -> dict:
    """写 qa_access_logs；失败仅日志，不阻断用户"""
    try:
        await ctx["log_repo"].insert({
            "session_id": state["session_id"],
            "user_id": state["user_id"],
            "question": state["question"],
            "answer": "".join(state["answer_chunks"]),
            "recalled_unit_ids_json": json.dumps([(u["unit_id"], u["score"]) for u in state.get("recalled_units", [])]),
            "authorized_unit_ids_json": json.dumps(state.get("authorized_unit_ids", [])),
            "unauthorized_unit_ids_json": json.dumps(state.get("unauthorized_unit_ids", [])),
            **state["usage"],
            "response_time_ms": state["usage"].get("response_time_ms"),
            "source": state["usage"].get("source", "llm"),
        })
    except Exception as exc:
        loguru_logger.warning("qa_access_log.write.fail session={} error={}", state["session_id"], exc)
    return {}
```

### 5.6 AIService 流式输出

```python
class AIService:
    async def chat_stream(self, req: ChatStreamRequest, user: CurrentUser) -> AsyncIterator[bytes]:
        """FastAPI StreamingResponse 异步生成器"""
        yield sse_event("ready", {"session_id": req.session_id})
        initial_state = await self._build_initial_state(req, user)
        ctx = self._build_context()
        graph = build_chat_graph()

        async for event in graph.astream(initial_state, context=ctx, stream_mode="events"):
            kind = event["event"]
            if kind == "on_chain_end" and "events_to_emit" in event["data"].get("output", {}):
                for e in event["data"]["output"]["events_to_emit"]:
                    yield sse_event(e["type"], e["data"])
            elif kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"].content
                if chunk:
                    yield sse_event("delta", {"text": chunk})
            elif kind == "on_node_end" and event["node"] == "permission_filter":
                yield sse_event(
                    "unauthorized", {"unit_ids": event["data"]["output"]["unauthorized_unit_ids"]}
                )
            elif (
                kind == "on_node_end"
                and event["node"] == "permission_filter"
                and event["data"]["output"].get("reranked_units")
            ):
                for u in event["data"]["output"]["reranked_units"]:
                    yield sse_event("citation", {"unit_id": u["unit_id"], "score": u["score"]})

        yield sse_event("final", {"answer": ..., "usage": ...})
```

### 5.7 ChatSessionService

```python
class ChatSessionService:
    async def create(self, user: CurrentUser, req: CreateSessionRequest) -> ChatSessionResponse:
        session_id = str(uuid.uuid4())
        await self._repo.insert(
            session_id=session_id,
            user_id=user.id,
            title=req.title or "新会话",
            history_json={"turns": [], "slots": {}, "pending_turn": None},
        )
        return await self.get(session_id, user)

    async def append_turn(self, session_id: str, user: CurrentUser, turn: dict) -> None:
        """完成问答后追加 turn + 清 pending_turn"""
        await self._repo.append_turn_and_clear_pending(session_id, user.id, turn)

    async def list(
        self, user: CurrentUser, page: int, page_size: int
    ) -> tuple[list[SessionListItem], int]: ...

    async def get(self, session_id: str, user: CurrentUser) -> ChatSessionResponse:
        ...
        # 校验 user_id == 当前用户

    async def delete(self, session_id: str, user: CurrentUser) -> None: ...
```

### 5.8 异常

```python
class SessionNotFoundError(ResourceNotFoundError):
    error_code = "chat_session_not_found"


class SessionPermissionDeniedError(PermissionDeniedError):
    error_code = "chat_session_not_owned"


class NoRecallError(ValidationError):
    error_code = "no_recall"  # 触发 interrupt


class NoRecallWithPermissionError(ValidationError):
    error_code = "no_recall_with_permission"
```

---

## 6. 前端设计

### 6.1 页面与组件

| 页面 | 路径 | 关键组件 |
| --- | --- | --- |
| AI 对话工作台 | `views/ai/ChatWorkbenchView.vue` | `SessionList` / `MessageStream` / `CitationCard` / `UnauthorizedCard` / `InterruptHint` / `ChatInput` / `FaqBadge` |

### 6.2 关键组件 props

```typescript
// SessionList.vue
interface SessionListProps {
  sessions: SessionListItem[];
  activeId: string | null;
}
interface SessionListEmits {
  (e: "select", id: string): void;
  (e: "delete", id: string): void;
  (e: "new"): void;
}

// MessageStream.vue
interface MessageStreamProps {
  turns: ChatTurn[];
  streaming: { kind: "delta" | "citation" | "unauthorized" | "interrupt"; data: any }[];
}

// CitationCard.vue
interface CitationCardProps {
  unitId: number;
  title: string;
  score: number;
}

// UnauthorizedCard.vue（不展示正文）
interface UnauthorizedCardProps {
  unitIds: number[];
  requestable: boolean;       // 是否有"申请权限"入口
}

// ChatInput.vue
interface ChatInputProps {
  disabled: boolean;
  placeholder: string;
}
interface ChatInputEmits {
  (e: "send", text: string): void;
}
```

### 6.3 关键状态

| 状态 | UI 反馈 |
| --- | --- |
| `ready` | 工作台显示"会话已就绪"小提示 |
| `progress` | 流式过程中顶部进度条（可选） |
| `delta` | 消息流追加 token |
| `citation` | 消息流末尾追加引用卡片 |
| `unauthorized` | 引用侧栏新增"无权访问"徽章 + 申请权限入口 |
| `interrupt` | 输入框保留 + 顶部提示"未找到相关知识，请补充问题" |
| `final` | 消息流收尾 + 流式统计展示 |
| `error` | 全局错误条 + 消息流不展示部分内容 |

### 6.4 API 方法

```typescript
// frontend/src/api/ai.ts
export const aiApi = {
  createSession: (data: CreateSessionRequest) => api.post<ChatSessionResponse>("/ai/sessions", data).then(r => r.data),
  listSessions: () => api.get<SessionListItem[]>("/ai/sessions").then(r => r.data),
  getSession: (id: string) => api.get<ChatSessionResponse>(`/ai/sessions/${id}`).then(r => r.data),
  deleteSession: (id: string) => api.delete(`/ai/sessions/${id}`),

  chatStream: async (
    data: ChatStreamRequest,
    handlers: {
      onReady?: (e: any) => void;
      onDelta?: (text: string) => void;
      onCitation?: (e: CitationEvent) => void;
      onUnauthorized?: (e: UnauthorizedEvent) => void;
      onInterrupt?: (e: InterruptEvent) => void;
      onFinal?: (e: FinalEvent) => void;
      onError?: (e: any) => void;
    }
  ): Promise<void> => {
    const resp = await fetch("/api/v1/ai/chat/stream", {
      method: "POST",
      headers: { "Authorization": `Bearer ${getToken()}`, "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    await consumeSSE(resp, handlers);
  },

  chatResume: (data: ChatResumeRequest, handlers: SameHandlers) => fetch(...).then(consumeSSE),
};
```

### 6.5 SSE 消费

使用 `fetch + ReadableStream`（`EventSource` 不支持自定义 header）。`consumeSSE(resp, handlers)` 解析 `event: ` / `data: ` 双行，路由到对应 handler。

---

## 7. OpenAPI 契约

### 7.1 POST /api/v1/ai/chat/stream

**响应**：`text/event-stream`

事件顺序（典型一次问答）：
```
event: ready     data: {"session_id":"..."}
event: delta     data: {"text":"..."}
event: delta     data: {"text":"..."}
event: citation  data: {"unit_id":42,"title":"...","score":0.91}
event: unauthorized data: {"unit_ids":[88]}
event: final     data: {"answer":"...","usage":{...}}
```

或 interrupt 路径：
```
event: ready
event: interrupt data: {"reason":"no_recall_with_permission","session_id":"..."}
```

### 7.2 POST /api/v1/ai/chat/resume

请求：`{ session_id, question }`，与 stream 一致；服务端自动检测 `pending_turn` 续接。

### 7.3 错误码
- 404 `chat_session_not_found`
- 403 `chat_session_not_owned`
- 401 `authentication_required`

---

## 8. 异步与适配器

| 项 | 描述 |
| --- | --- |
| LLM | `langchain_openai.ChatOpenAI`（OpenAI-compatible base_url）；stream_mode=events |
| Embedding | 见 M3（FAQ 缓存命中校验不重新嵌入，仅校验 unit_updated_at） |
| 鉴权 | 复用 M3 `KnowledgePermissionService.compute_user_permission_bitmap_sync`（纯函数，无 IO） |
| Redis | FAQ 缓存（key=`faq:cache:<hash>`，HSET 含 answer / related_unit_id / unit_updated_at）+ 鉴权位图 |
| APScheduler | 后续 P4 阶段接入 FAQ 挖掘 / 缺口识别定时任务 |

---

## 9. 权限、审计与日志

### 9.1 关键事件日志

| 事件 | 字段 |
| --- | --- |
| FAQ 缓存命中 | log:info `event=ai.faq_cache.hit unit_id=...` |
| 鉴权过滤 | log:debug `event=ai.permission_filter authorized=N unauthorized=M` |
| interrupt | log:info `event=ai.interrupt reason=... session=...` |
| LLM 调用 | log:info `event=ai.llm.call tokens=... model=... response_time=...` |
| record_log 失败 | log:warn `event=ai.log.fail session=...` |

### 9.2 脱敏
- 历史问答不写入日志
- Token 仅记录消耗量，不记录具体内容

---

## 10. 测试与验收

### 10.1 关键用例

| 用例 | 验证 |
| --- | --- |
| `test_create_session_returns_uuid` | 创建会话返回 UUID |
| `test_chat_stream_full_pipeline` | 召回 → 鉴权 → 拼装 → 生成 → final 事件顺序正确 |
| `test_chat_stream_faq_cache_hit` | FAQ 命中跳过 retrieve + permission_filter + assemble |
| `test_chat_stream_unauthorized_cards` | 无权单元不进入 answer，事件流输出 unauthorized |
| `test_chat_stream_interrupt_when_no_recall` | 召回为空触发 interrupt 事件 |
| `test_chat_stream_interrupt_when_no_authorized` | 鉴权后为空触发 interrupt |
| `test_chat_resume_uses_pending_turn` | resume 携带 pending_turn |
| `test_chat_record_log_persists_units` | 单元 id 写入 JSON 字段 |
| `test_chat_history_window_trim_to_6` | 历史窗口限制 |
| `test_rerank_dynamic_cut` | 动态断崖生效 |

### 10.2 验收 checkbox
- [ ] 8 节点编排完整工作
- [ ] FAQ 缓存命中率（演示）≥ 30%
- [ ] SSE 8 种事件类型均能产生
- [ ] interrupt 状态可被 resume 续接
- [ ] 流式输出 P95 < 3s

---

## 11. 待确认项

| 项 | 默认假设 |
| --- | --- |
| LangGraph runtime | `astream` + `stream_mode="events"` |
| History 窗口 | 6 轮 |
| 动态断崖参数 | GAP_RATIO=0.75, MIN_TOPK=1, MAX_TOPK=10 |
| 鉴权位图缓存策略 | M3 维护，本模块只读 |
| interrupt 触发条件 | authorized_unit_ids 为空 或 recalled_units 为空 |
| LLM 限流 | 演示期不限流 |