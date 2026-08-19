# kb_mp 平台介绍

## 一、产品定位

kb_mp（Knowledge Base Management Platform）是面向企业内部知识资产管理的 AI 平台，
核心解决三类问题：

1. **知识沉淀**：把分散在 Excel / 邮件 / 文档里的经验沉淀成可检索的结构化单元
2. **知识检索**：基于向量语义 + 四维权限，让员工用自然语言快速找到答案
3. **知识运营**：通过数据看板识别高频问题与知识缺口，持续反哺资产建设

## 二、核心能力

### 2.1 文档智能解析

- 支持 Markdown / PDF / Word / TXT
- 自动切片（chunk_size=512 + overlap=64）
- SHA-256 去重，避免重复入库
- 后台异步向量化（FastAPI BackgroundTasks + asyncio.create_task）

### 2.2 向量语义检索

- BGE-M3（1024 维）或 OpenAI text-embedding-3-small（1536 维）
- Milvus 2.5+ COSINE 相似度 + HNSW 索引
- 可选 BGE-Reranker-Large 二次精排

### 2.3 AI 鉴权问答

- LangGraph 8 节点编排（faq_cache_lookup → retrieve → rerank → permission_filter →
  interrupt → assemble_prompt → generate → record_log）
- SSE 流式输出（8 事件类型：ready/progress/delta/citation/unauthorized/interrupt/final/error）
- 鉴权位图（Redis bitmap，5 分钟 TTL）+ MySQL 二级兜底
- 中断机制：召回为空 / Top-1 评分 < 0.2 时挂起等用户补充

### 2.4 数据看板

- 5 端点：metrics / question-rankings / unit-rankings / token-stats / response-time-stats
- 时间桶（24h / 7d / 30d）
- Top-10 高频问题 + Top-10 高贡献单元

### 2.5 FAQ 沉淀

- AI 自动挖掘（qa_access_logs 频次统计）
- 审核发布（pending_review → published / rejected）
- Redis 缓存同步 + 版本校验（unit_updated_at_snapshot）

### 2.6 知识缺口识别

- 同问题 ≥3 次未命中 → 识别为 gap
- 一键建档（create-unit-from-gap）

## 三、技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.12 + FastAPI + SQLAlchemy 2.0 (async) + Pydantic v2 |
| AI | LangChain + LangGraph + OpenAI SDK |
| 向量 | BGE-M3 / OpenAI Embedding + Milvus 2.5 |
| 缓存 | Redis 7 (bitmap + FAQ cache) |
| 数据库 | MySQL 8.0 + utf8mb4 |
| 前端 | React 18 + Vite + TypeScript + Tailwind |
| 部署 | Docker Compose + GitHub Actions (CI/CD) |

## 四、6 大模块

| 模块 | 说明 |
|---|---|
| M1 认证鉴权 | JWT + bcrypt + 17 权限码 + 鉴权位图 |
| M2 组织架构 | 部门树 + 用户/角色 CRUD |
| M3 知识资产 | 单元 CRUD + 导入 + 四维权限 + check-permissions |
| M4 AI 对话 | LangGraph 8 节点 + SSE 流式 + 多轮会话 |
| M5 数据看板 | 5 端点 + 趋势分桶 |
| M6 知识沉淀 | FAQ CRUD + 审核 + 缓存 + 缺口识别 |