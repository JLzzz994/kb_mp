# kb_mp SSE 流式事件约定

## 1. 端点

```
POST /api/v1/ai/chat/stream
Content-Type: application/json
Authorization: Bearer <token>

{
  "session_id": "uuid-xxx",
  "question": "kb_mp 是什么？"
}
```

## 2. 8 种 SSE 事件

| event | data 字段 | 含义 |
|---|---|---|
| `ready` | `{session_id}` | 会话就绪，开始处理 |
| `progress` | `{stage, progress}` | 节点进度（0-100） |
| `citation` | `{units: [{id, title, score}]}` | 召回引用（含 score） |
| `unauthorized` | `{unit_ids: [...]}` | 召回但被鉴权拦截的单元 |
| `interrupt` | `{interrupt_id, reason, message}` | 中断，等待用户补充 |
| `delta` | `{chunk: "..."}` | LLM 流式输出片段 |
| `final` | `{answer, tokens, sources}` | 完整答案 + token 用量 |
| `error` | `{code, message}` | 异常终止 |

## 3. LangGraph 8 节点 → progress stage 映射

| 节点 | stage | progress |
|---|---|---|
| faq_cache_lookup | `faq_cache_lookup` | 10 |
| retrieve | `retrieve` | 30 |
| rerank | `rerank` | 40 |
| permission_filter | `permission_filter` | 50 |
| interrupt | `interrupt` | 60（仅触发时） |
| assemble_prompt | `assemble_prompt` | 70 |
| generate | `generate` | 80（持续发 delta） |
| record_log | `record_log` | 95 |

## 4. 完整流示例

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache

event: ready
data: {"session_id": "uuid-xxx"}

event: progress
data: {"stage": "faq_cache_lookup", "progress": 10}

event: progress
data: {"stage": "retrieve", "progress": 30}

event: citation
data: {"units": [{"id": 1, "title": "kb_mp 平台介绍", "score": 0.92}]}

event: progress
data: {"stage": "permission_filter", "progress": 50}

event: progress
data: {"stage": "assemble_prompt", "progress": 70}

event: progress
data: {"stage": "generate", "progress": 80}

event: delta
data: {"chunk": "kb_mp"}

event: delta
data: {"chunk": " 是"}

event: delta
data: {"chunk": " 企业"}

event: delta
data: {"chunk": " 知识"}

event: delta
data: {"chunk": " 库"}

event: delta
data: {"chunk": " 管理"}

event: delta
data: {"chunk": " 平台"}

event: final
data: {
  "answer": "kb_mp 是企业知识库管理平台...",
  "tokens": {"prompt": 100, "completion": 50, "total": 150},
  "sources": [{"id": 1, "title": "kb_mp 平台介绍"}]
}
```

## 5. 中断流示例

```http
event: ready
data: {"session_id": "uuid-yyy"}

event: progress
data: {"stage": "faq_cache_lookup", "progress": 10}

event: progress
data: {"stage": "retrieve", "progress": 30}

event: progress
data: {"stage": "permission_filter", "progress": 50}

event: interrupt
data: {
  "interrupt_id": "int-zzz",
  "reason": "no_recall",
  "message": "未找到相关内容，请补充关键词或描述"
}
```

客户端收到 interrupt 后：

```bash
curl -X POST http://localhost:8000/api/v1/ai/chat/resume \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "uuid-yyy",
    "interrupt_id": "int-zzz",
    "additional_info": "kb_mp 是知识库管理平台"
  }'
```

## 6. 鉴权未通过流示例

```http
event: ready
data: {"session_id": "uuid-www"}

event: progress
data: {"stage": "retrieve", "progress": 30}

event: citation
data: {"units": [{"id": 3, "title": "研发中心技术规范", "score": 0.88}]}

event: unauthorized
data: {"unit_ids": [3]}

event: interrupt
data: {
  "interrupt_id": "int-vvv",
  "reason": "no_authorized_recall",
  "message": "命中但未授权，请联系管理员"
}
```

## 7. 错误流示例

```http
event: ready
data: {"session_id": "uuid-eee"}

event: progress
data: {"stage": "retrieve", "progress": 30}

event: error
data: {
  "code": "milvus_unavailable",
  "message": "向量检索服务不可用，请联系运维"
}
```

## 8. 客户端解析参考（JavaScript）

```typescript
const eventSource = new EventSource('/api/v1/ai/chat/stream', {
  // 注意：EventSource 不支持 POST，需改用 fetch + ReadableStream
});

const response = await fetch('/api/v1/ai/chat/stream', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify({ session_id, question })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { value, done } = await reader.read();
  if (done) break;

  const chunk = decoder.decode(value);
  const lines = chunk.split('\n');

  for (const line of lines) {
    if (line.startsWith('event: ')) {
      const event = line.slice(7);
      // 处理事件
    } else if (line.startsWith('data: ')) {
      const data = JSON.parse(line.slice(6));
      // 处理数据
    }
  }
}
```