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
| Vue 3 | 当前代码为 React，需继续迁移 |

## 本地开发

```bash
# 后端
uv sync --all-extras
uv run uvicorn app.api.app:app --reload --port 8000

# 初始化 ERP/WMS 业务演示组织
uv run python scripts/seed.py --reset

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

权限仍然挂在 MySQL 的 `knowledge_unit` 上；Milvus 只负责 chunk 级检索。
这样可以同时满足“细粒度召回”和“文档级权限治理”。

MinerU 采用外部 CLI/服务方式接入，不强塞进默认 `uv sync --all-extras`，避免 CI 和普通开发环境被大型模型依赖拖慢。安装 MinerU 后，`DOCUMENT_PARSER_BACKEND=auto` 会对 PDF/DOCX 优先尝试 MinerU；也可以配置 `MINERU_API_URL` 连接独立解析服务。

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

## 后续建议

为了让仓库与最新版简历进一步一致，下一阶段建议：

1. 增加 RAGAS/固定评测集与 bad case 回流，量化 Recall@K、MRR、Faithfulness 和答案采纳率。
2. 增加文档版本更新后的 chunk 增量重建、旧向量清理和索引一致性校验。
3. 把当前 React 前端正式迁移到 Vue 3，并保留现有产品知识运营交互。
