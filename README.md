# 慧策 ERP/WMS 产品知识运营平台

本分支将原通用 `kb_mp` 企业知识库，业务化为面向电商 ERP/WMS 场景的产品知识运营平台。
主要服务 **产品、实施、客服、客户成功** 团队，围绕订单履约、商品/SKU、库存、仓储/WMS、采购、售后、财务/结算等知识提供统一导入、权限治理、检索问答、FAQ 审核和知识缺口闭环。

> 分支：`feat/huice-erp-wms-knowledge-ops`

## 业务目标

典型问题包括：

- 旺店通订单为什么没有进入待审核，应该检查哪些前置条件？
- WMS 可用库存和锁定库存分别在什么场景变化？
- 店铺退款后 ERP 与 WMS 的逆向流程如何衔接？
- 实施顾问排查库存同步异常时需要收集哪些信息？
- 客服能否查看某类产品内部排障文档？无权限时系统如何处理？

AI 不直接修改订单、退款、库存或资金状态。涉及高风险业务动作时，只返回知识依据、操作前置条件、权限要求和人工处理流程。

## 本分支新增

### 1. ERP/WMS 业务 Prompt

`app/business/erp_wms.py`

- 按关键词识别订单、商品/SKU、库存、仓储、采购、售后、结算知识域。
- 将产品、实施、客服、客户成功的服务对象注入系统 Prompt。
- 强制只基于鉴权后知识回答。
- 对退款、资金、库存调整、订单状态变更等高风险动作增加人工处理边界。
- 知识不足时要求补充产品版本、平台渠道、业务场景或异常现象。

### 2. ERP/WMS 业务化问答链路

现有 8 节点主链路继续保留：

```text
FAQ Cache
  -> Retrieve
  -> Rerank
  -> Permission Filter
  -> Interrupt
  -> Assemble Prompt
  -> Generate
  -> Record Log
```

Milvus/Embedding 不可用时，演示分支不再返回通用 mock，而是返回 ERP/WMS 业务化 demo citations，方便本地验证完整的“召回 -> 鉴权 -> 回答 -> 引用”链路。

### 3. 业务组织与权限

seed 数据调整为：

- 产品中心
- 实施交付中心
- 商家客服中心
- 客户成功中心

演示角色：

- 平台管理员
- 产品知识管理员
- 业务查询用户

权限控制仍由原有 RBAC + 知识单元权限机制负责，业务 Prompt 不参与权限判定。

### 4. 产品知识运营界面

控制台文案调整为 ERP/WMS 产品知识运营场景，包括：

- 知识运营看板
- 产品文档导入
- 知识资产
- ERP/WMS 智能问答
- FAQ 审核
- 知识缺口

## 技术实现

### 后端

- Python / FastAPI
- SQLAlchemy / Alembic
- Milvus
- Redis
- MinIO
- Embedding / LLM 可配置 provider
- 8 节点 RAG 工作流
- SSE 流式问答
- RBAC + 知识单元级权限过滤

### 前端现状

当前仓库实际前端是 **React + Vite + TypeScript/TSX**。
原 `master` README 中“Vue 3”与真实代码不一致，本分支先修正业务与 RAG 主链路，不继续把 React 代码描述成 Vue 3。

如果要与简历中的 Vue 3 技术栈完全一致，下一步应单独迁移前端，而不是只改 README。

## 与简历项目口径的对应关系

| 简历能力 | 当前分支落点 |
|---|---|
| ERP/WMS 产品知识平台 | 已业务化 |
| 产品/实施/客服/客户成功 | seed + Prompt + UI 已覆盖 |
| 文档导入/切片/向量入库 | 已升级为 MinerU 可选结构化解析 + 页码/章节切片 + chunk 级 Milvus |
| Milvus 检索 | 已有 |
| 权限过滤后入 Prompt | 已有并强化 |
| FAQ 审核 | 已有 |
| 知识缺口 | 已有 |
| SSE 引用返回 | 已有 |
| Query Rewrite / HyDE / RRF / BGE-Reranker | 已落地：关键词 + rewrite 向量 + HyDE 向量三路召回，RRF 融合，BGE 可配置精排 |
| MinerU | 已接入 CLI/远程 API 模式，auto 失败时回退 pypdf/python-docx |
| 固定评测 / bad case / RAGAS | 已落地固定 ERP/WMS 评测集、Hit@K/Recall@K/MRR、bad-case 分类与可选 RAGAS runner |
| 知识更新 / 索引一致性 | 已落地 unit 级增量重建、旧向量清理、index-status、批量 audit/repair |
| Vue 3 | 当前代码为 React，需继续迁移 |

## 本地开发

```bash
# 后端
uv sync --all-extras
uv run uvicorn app.api.app:app --reload --port 8000

# 初始化 ERP/WMS 业务演示组织
uv run python scripts/seed.py --reset

# 可选：启用 MinerU
# 1) 保证 mineru 命令在 PATH 中；或
# 2) 启动独立 mineru-api，并设置 MINERU_API_URL
# 默认 auto 模式在 MinerU 不可用时自动回退原生解析器

# 前端
cd frontend
npm install
npm run dev
```

## 部署

```bash
cd deploy
docker compose up -d
```

## 测试

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest -v --ignore=tests/test_e2e_t7_real_vectorize.py
```

## 当前文档入库链路

```text
PDF / DOCX / MD / TXT
  -> ParserFactory
  -> PDF/DOCX: MinerU(auto/mineru) -> content_list.json
  -> native fallback: pypdf / python-docx / markdown / txt
  -> StructuredSplitter
       保留 section_path / page_start / page_end / block_types
  -> MySQL: 一文档一个 knowledge_unit（权限对象）
  -> BGE-M3 embed_batch(chunks)
  -> Milvus kb_unit_chunks_v2（一个 unit 多个 chunk）
```

权限仍然挂在 MySQL 的 `knowledge_unit` 上；Milvus 只负责 chunk 级检索。旧 `kb_units` collection 不做原地兼容迁移，本分支默认使用新 collection `kb_unit_chunks_v2`。
这样可以同时满足“细粒度召回”和“文档级权限治理”。

MinerU 采用外部 CLI/服务方式接入，不强塞进默认 `uv sync --all-extras`，避免 CI 和普通开发环境被大型模型依赖拖慢。安装 MinerU 后，`DOCUMENT_PARSER_BACKEND=auto` 会对 PDF/DOCX 优先尝试 MinerU；也可以配置 `MINERU_API_URL` 连接独立解析服务。

## 知识更新与索引一致性

新导入源文件会从临时 UUID 文件归档成 `storage/uploads/{unit_code}.{ext}`，因此后续能够重新定位原 PDF/DOCX。

更新策略：

```text
PATCH summary
  -> 只改 MySQL，不动向量

PATCH title/category
  -> status=vector_pending
  -> 保留 embedding/page/section
  -> 仅更新 Milvus chunk 元数据
  -> status=active

PATCH content
  -> status=vector_pending
  -> 从 DB 新正文重新结构化切片
  -> 先完成 Embedding
  -> 删除该 unit 旧 chunks
  -> 写入新 generation chunks
  -> status=active

POST /api/v1/knowledge-units/{id}/reindex
  -> 如果归档源文件存在且重新解析文本 hash == DB content_hash
       优先按原文件重建，保留页码/章节
     否则
       从 DB 正文重建，避免旧源文件覆盖人工编辑
```

RAG 鉴权前还会查询 MySQL，只允许 `status=active` 的知识单元进入 Prompt。
因此 `vector_pending` 的旧向量、已删除 unit 的 orphan vector 都不会作为有效证据返回。

删除顺序是：**Milvus chunks -> MySQL unit -> 本地归档源文件**。如果向量清理失败，删除操作返回索引同步错误，不先删数据库记录。

当前是 **unit 级增量重建**：只重建发生变化的知识单元，不全量刷新 collection；并未把它描述成 chunk-diff 级增量更新。

运维接口和命令：

```bash
# 单个知识单元查看一致性
GET /api/v1/knowledge-units/{id}/index-status

# 单个知识单元人工重建
POST /api/v1/knowledge-units/{id}/reindex

# 批量 MySQL / Milvus 一致性巡检
uv run python scripts/check_index_consistency.py

# 显式修复不一致 unit
uv run python scripts/check_index_consistency.py --repair
```

## 当前混合检索链路

```text
用户问题
  -> Query Rewrite
  -> HyDE hypothetical document
  -> MySQL keyword recall ------------------┐
  -> Milvus(rewritten query) vector recall -+-> RRF -> BGE-Reranker -> 动态截断
  -> Milvus(HyDE document) vector recall ----┘
  -> 四维权限过滤
  -> Prompt
  -> LLM + citation
```

RRF 只使用各通道排名，不直接比较 MySQL 关键词分数与 Milvus cosine score；BGE-Reranker 开启后使用交叉编码器分数重新排序。模型不可用时自动退回 RRF 排名，不阻断主链路。

## RAG 评测闭环

固定评测集位于 `evals/datasets/erp_wms_fixed.jsonl`，覆盖订单履约、库存/WMS、售后以及跨域问题。

```bash
# 确定性检索评测：Hit@K / Recall@K / MRR + bad case
uv run python scripts/evaluate_retrieval.py

# 可选 RAGAS：需要真实回答 trace + evaluator LLM
uv run --with ragas==0.4.3 python scripts/evaluate_ragas.py \
  --input evals/results/rag_traces.jsonl
```

普通 CI 不调用 RAGAS 评审模型，避免每次提交消耗外部模型 token；RAGAS runner 当前评估 Context Precision、Context Recall、Faithfulness、Factual Correctness。

## 后续建议

为了让仓库与最新版简历进一步一致，下一阶段建议：

1. 把当前 React 前端正式迁移到 Vue 3，并保留现有产品知识运营交互。
2. 多实例部署时把本地源文件归档替换为 MinIO/object storage，并增加对象版本号。
3. 在有真实 Milvus/BGE/LLM 的独立 evaluation 环境沉淀版本基线，对 Recall@K、MRR、Faithfulness 做发布门禁。
