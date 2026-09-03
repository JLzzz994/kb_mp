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

### 前端

当前分支已从原 React/TSX 实现真实迁移为 **Vue 3 + Vite + TypeScript + Pinia + Vue Router**。

- 登录、权限菜单、路由守卫已迁移为 Vue/Pinia。
- 产品文档导入、知识资产、ERP/WMS 智能问答已迁移为 Vue SFC。
- 知识资产页可直接查看 index-status，并由有权限用户触发单 unit reindex。
- 知识资产详情已接入四维权限可视化编辑：global / department / role / user；global 与 scoped 权限互斥，scoped 维度之间按 OR 生效。
- SSE 问答继续保留 citation / unauthorized / interrupt / final 事件处理。
- 知识运营看板已从 Recharts 改为 **ECharts**，展示 Token 与响应时间趋势。
- 用户页已接入创建、更新、启停用、重置密码；角色页按真实后端能力提供权限全量替换。
- 业务团队页已接入部门树 CRUD，并在前后端同时阻止循环 parent 关系。
- FAQ 页已接入创建、审核通过/拒绝、下线；知识缺口页已接入“一键建档 -> 最小权限 -> 索引 -> resolved”。
- 原 React、React Router、Radix/shadcn TSX 源码与依赖已从该分支移除。

## 与简历项目口径的对应关系

| 简历能力 | 当前分支落点 |
|---|---|
| ERP/WMS 产品知识平台 | 已业务化 |
| 产品/实施/客服/客户成功 | seed + Prompt + UI 已覆盖 |
| 文档导入/切片/向量入库 | 已升级为 MinerU 可选结构化解析 + 页码/章节切片 + chunk 级 Milvus |
| Milvus 检索 | 已有 |
| 权限过滤后入 Prompt | 已有并强化 |
| 四维知识权限运营 | 已接 Vue 编辑器 + 后端全量替换；global 独占，department/role/user OR，target ID 必须真实存在 |
| FAQ 审核 | 已有 |
| 知识缺口 | 已有 |
| SSE 引用返回 | 已有 |
| Query Rewrite / HyDE / RRF / BGE-Reranker | 已落地：关键词 + rewrite 向量 + HyDE 向量三路召回，RRF 融合，BGE 可配置精排 |
| MinerU | 已接入 CLI/远程 API 模式，auto 失败时回退 pypdf/python-docx |
| 固定评测 / bad case / RAGAS | 已落地固定 ERP/WMS 评测集、Hit@K/Recall@K/MRR、bad-case 分类与可选 RAGAS runner |
| 真实模型评测基线 | 已落地固定语料自动准备、真实 BGE-M3/Milvus fail-fast、RRF vs BGE-Reranker 同候选 A/B、baseline 回归门禁与真实 LLM trace 采集；数值需真实环境执行后产生 |
| 知识更新 / 索引一致性 | 已落地 unit 级增量重建、旧向量清理、index-status、批量 audit/repair |
| MinIO 源文件版本管理 | 已落地 local/minio 双后端，按 unit_code + content_hash 版本化对象 key |
| Vue 3 / Pinia / ECharts | 已完成前端真实迁移，React/TSX 残留扫描为 0 |
| 组织/RBAC 管理 | 用户创建/更新/启停/重置密码、部门 CRUD、角色权限分配已接真实 API |
| FAQ / 知识缺口运营 | FAQ 创建/审核/下线、缺口建档与索引闭环已接真实 API |

## 本地开发

```bash
# 后端
uv sync --locked --all-extras
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
uv lock --check
uv sync --locked --all-extras
uv run ruff format --check .
uv run ruff check .
uv run pytest -v --ignore=tests/test_e2e_t7_real_vectorize.py

# CI 还会启动真实 MinIO 容器执行
RUN_MINIO_INTEGRATION=1 uv run pytest tests/test_source_storage_minio_integration.py -v
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

新导入源文件使用可切换的 SourceStorage：

```text
SOURCE_STORAGE_BACKEND=local
  -> storage/uploads/sources/{unit_code}/{content_hash}.{ext}

SOURCE_STORAGE_BACKEND=minio
  -> kb-source-docs/sources/{unit_code}/{content_hash}.{ext}
```

Docker Compose 默认让应用使用已有 MinIO 服务的独立 `kb-source-docs` bucket；MinIO bucket 在首次归档时幂等创建。对象 key 使用解析后正文的 SHA-256 `content_hash` 作为版本号，因此旧源文件不会覆盖新版本。

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
  -> SourceStorage 按 unit_code + DB content_hash 查找版本化源文件
  -> MinIO 后端先临时物化到本地，再交给 MinerU/parser
  -> 如果重新解析文本 hash == DB content_hash
       按原文件重建，保留页码/章节
     否则
       从 DB 正文重建，避免旧源文件覆盖人工编辑
  -> MinIO 临时物化文件用完即清理
```

RAG 鉴权前还会查询 MySQL，只允许 `status=active` 的知识单元进入 Prompt。
因此 `vector_pending` 的旧向量、已删除 unit 的 orphan vector 都不会作为有效证据返回。

删除主顺序是：**Milvus chunks -> MySQL unit -> SourceStorage 源文件**。如果向量清理失败，数据库记录不会先删；数据库删除成功后若对象存储清理失败，只留下不可检索 orphan source，并记录告警，不把业务删除回滚成半删除状态。

当前是 **unit 级增量重建**：只重建发生变化的知识单元，不全量刷新 collection；并未把它描述成 chunk-diff 级增量更新。


### MinIO 源文件版本策略

`app/infrastructure/source_storage.py` 统一封装本地和 MinIO：

- 上传解析前仍先写临时本地文件，MinerU / native parser 无需感知对象存储；
- DB 成功后再把源文件归档到 SourceStorage；
- MinIO SDK 的网络 I/O 通过 `asyncio.to_thread`，避免阻塞 FastAPI Event Loop；
- reindex 只拉取和当前 `content_hash` 匹配的对象版本；
- 人工 PATCH 正文后 hash 变化但没有对应新源文件时，自动回退数据库正文；
- 兼容旧 `storage/uploads/{unit_code}.{ext}` 本地文件；
- Local/MinIO 单元测试保留 fake client 做确定性验证；
- GitHub Actions 另起真实 MinIO 容器，执行 archive -> stat/download -> materialize -> delete 的网络 smoke test。


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

真实模型基线工具位于：

```text
scripts/prepare_evaluation_corpus.py
  -> 固定 expected_sources 自动准备语料
  -> 真实 BGE-M3 embedding
  -> 独立 Milvus collection
  -> fail-fast，不允许 demo/vector fallback

scripts/compare_retrieval_baseline.py
  -> 同一份 RRF 候选
  -> RRF-only vs BGE-Reranker
  -> Hit@K / Recall@K / MRR + latency
  -> dataset SHA / git SHA / 模型 metadata/snapshot/weight-manifest 与运行环境指纹
  -> 显式 --write-baseline 才写基线
  -> --baseline + tolerance 做回归门禁

scripts/capture_rag_eval_traces.py
  -> real retrieve
  -> BGE rerank
  -> permission filter
  -> prompt
  -> real OpenAI-compatible LLM
  -> rag_traces.jsonl + trace manifest
  -> RAGAS fixed threshold + historical baseline gate
```

详细运行方式见 `evals/README.md`。仓库还提供 **Real RAG Evaluation Baseline** 手工 Actions workflow，
要求 self-hosted Linux runner、真实 Milvus/模型路径和独立 `EVAL_DATABASE_URL`；可选启用真实 LLM + RAGAS。
运行报告默认落在被 Git 忽略的 `evals/results/`，workflow 只上传 artifact，不自动提交 baseline。

当前仓库**没有预置任何真实 BGE/RAGAS 数值**，因此不能把工具链存在等同于已经取得某个 Recall@K、MRR 或 Faithfulness 结果。

## 后续建议

下一阶段建议：

1. 在真实 BGE-M3 / BGE-Reranker / Milvus 环境执行已落地的 A/B 工具，人工确认后提交第一份真实 baseline；再用真实 LLM trace 跑 RAGAS。
2. 为 MinIO source bucket 增加 lifecycle/orphan 巡检策略；真实网络 smoke 已进入 CI，但不等同于生产容灾验证。
3. 将四维权限目标选择从当前单页组织数据加载继续优化为服务端搜索/分页，适配更大规模用户目录。
