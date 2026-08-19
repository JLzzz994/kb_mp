# ADR-0002: AI 鉴权流采用 LangGraph 8 节点

## 状态
已决定 (2026-08-19)

## 背景
AI 鉴权问答流程需要把"FAQ 缓存命中 / 向量召回 / 鉴权过滤 / 鉴权失败挂起 / Prompt 拼装 / 流式生成 / 访问日志"全部纳入一张图。

历史版本在概要设计、Spec M4、IMPL M4 之间出现 6 / 7 / 8 三种节点数描述：
- 概要设计 §5.2 节点表实际列出 8 个节点（含 `interrupt`），但标题写作 7
- §6 决策表与 §10 P2 验收点又把节点数写作 7 / 6
- ADR-0002 索引条目写作 6

## 决策
AI 鉴权流采用 LangGraph 8 节点，顺序与职责：

| # | 节点 | 职责 |
| --- | --- | --- |
| 1 | `faq_cache_lookup` | Redis hash 命中 + 知识单元版本校验 |
| 2 | `retrieve` | Milvus Top-20 向量检索 |
| 3 | `rerank` | 动态断崖截断（score[i+1]/score[i] < 0.75） |
| 4 | `permission_filter` | 拉用户权限位图 + 内存 OR 集合运算，输出 authorized + unauthorized |
| 5 | `interrupt` | 鉴权或召回为空时挂起，写 `chat_sessions.pending_turn` + 推 SSE `interrupt` 事件 |
| 6 | `assemble_prompt` | 系统提示 + 历史（≤6 轮，trim_messages）+ 引用上下文 |
| 7 | `generate` | LLM 流式输出 + Token 统计 |
| 8 | `record_log` | 写 `qa_access_logs`（失败不抛错） |

节点签名统一为 `(state: ChatState, ctx: GraphContext)`，去掉 LangGraph `Runtime[GraphContext]` 包装，便于直接 mock 与单测。

## 影响
- 概要设计 §5.2 标题、§6 决策表、§10 P2 验收点、ADR-0002 索引全部对齐 8 节点
- Spec M4 §1 范围与 §5.4 Graph 装配章节保持 8 个 `add_node` 调用
- IMPL-M4 §3 节点签名改为 `(state, ctx)`，§4 `graph.py` 不再写 `ctx = runtime.context`
- 阶段验收 Checklist（IMPL-M4 §9、Spec M4 §10.2）同步更新

## 备选方案
- 7 节点（合并 `interrupt` 到 `permission_filter` 的副作用分支）—— 拒绝，挂起逻辑需要独立节点便于单测
- 6 节点（把 `record_log` 放在 `generate` 内部）—— 拒绝，写库失败需要隔离不阻断用户流