# ERP/WMS RAG 评测闭环

本目录用于把“感觉回答不错”变成可重复的固定评测与 bad-case 回流。

## 1. 固定检索集

`datasets/erp_wms_fixed.jsonl` 当前包含订单履约、库存/WMS、售后及跨域问题。

每条样本包含：

- `case_id`
- `question`
- `expected_sources`
- `reference`
- `tags`

预期来源使用文件名而不是数据库自增 ID，因此重新导入知识库后评测集仍然稳定。

## 2. 确定性检索评测

先将 `交付物/03-示例数据` 的三份 ERP/WMS 演示知识导入当前环境，然后运行：

```bash
uv run python scripts/evaluate_retrieval.py
```

默认产出：

- `evals/results/retrieval_report.json`
- `evals/results/retrieval_bad_cases.jsonl`

核心指标：

- Hit@K：Top-K 是否至少命中一个正确来源。
- Recall@K：预期来源有多少被 Top-K 覆盖。
- MRR：第一个正确来源出现位置的倒数。
- bad case：`no_recall`、`source_miss`、`no_relevant_source`、`low_rank`、`low_confidence`。

脚本默认带质量门槛，低于阈值会返回非 0 exit code，便于后续挂到专门的 evaluation CI。

## 3. RAGAS 生成质量评测

RAGAS 不加入在线运行依赖，也不放进普通 CI，避免每次提交都调用评审 LLM。

先从真实 RAG 链路捕获 JSONL：

```json
{
  "case_id": "inventory-sync-001",
  "question": "WMS 库存同步异常排查前需要收集哪些信息？",
  "response": "模型实际回答",
  "reference": "人工标注参考答案",
  "retrieved_contexts": ["真实送入 Prompt 的上下文 1", "上下文 2"]
}
```

然后执行：

```bash
uv run --with ragas==0.4.3 python scripts/evaluate_ragas.py \
  --input evals/results/rag_traces.jsonl
```

输出：

- `evals/results/ragas_report.csv`
- `evals/results/ragas_bad_cases.jsonl`

当前评估：

- Context Precision
- Context Recall
- Faithfulness
- Factual Correctness

默认阈值分别为 0.80 / 0.80 / 0.85 / 0.80，可通过 CLI 参数调整。

## 4. bad-case 回流方式

建议按 reason 分桶处理：

| bad case | 优先检查 |
|---|---|
| no_recall | 文档是否入库、Query Rewrite/HyDE、召回通道 |
| source_miss | 关键词、Embedding、RRF、多知识域覆盖 |
| low_rank | RRF 参数、BGE-Reranker、文档切片粒度 |
| low_confidence | 原始知识质量、问题歧义、Embedding |
| context_precision:low | 召回噪声、重排和截断 |
| context_recall:low | 漏召回、知识缺失、Query 改写 |
| faithfulness:low | Prompt 约束、上下文质量、模型幻觉 |
| factual_correctness:low | 参考答案差异、知识版本、生成错误 |

修复后使用同一固定集重跑，并保存报告用于版本间对比。


## 5. 真实 BGE / Milvus 可复现基线

普通 CI 不下载 BGE-M3 / BGE-Reranker，也不伪造真实模型指标。真实基线需要显式提供模型目录和 Milvus 地址。

推荐使用独立评测 collection，例如 `kb_eval_chunks_v1`，避免污染业务 collection。

### 5.1 准备固定语料

```bash
uv run --with sentence-transformers \
  python scripts/prepare_evaluation_corpus.py \
  --milvus-url http://localhost:19530 \
  --collection kb_eval_chunks_v1 \
  --embedding-model /models/bge-m3
```

脚本只取固定集 `expected_sources` 引用的三份 ERP/WMS 演示知识，缺失时导入，并使用真实 BGE-M3 建 chunk 向量。评测语料统一配置为 global，便于后续生成质量评测；建议只在独立评测库执行。

任何以下情况都会直接失败，不会退化成 demo citation：

- BGE-M3 模型不可加载；
- Embedding 维度与 `EMBEDDING_DIM` 不一致；
- Milvus 不可连接；
- 固定知识文件缺失。

### 5.2 RRF 与 BGE-Reranker A/B

```bash
uv run --with sentence-transformers --with FlagEmbedding \
  python scripts/compare_retrieval_baseline.py \
  --milvus-url http://localhost:19530 \
  --collection kb_eval_chunks_v1 \
  --embedding-model /models/bge-m3 \
  --reranker-model /models/bge-reranker-large
```

同一个 query 只执行一次召回，再把**相同的 RRF 候选集**分别送入：

1. RRF-only 动态截断；
2. BGE-Reranker-Large 精排 + 动态截断。

因此报告中的 MRR/Recall 差异主要反映 reranker 排序影响，而不是两次召回差异。

默认输出：

- `evals/results/retrieval_ab_report.json`
- RRF-only Hit@K / Recall@K / MRR；
- BGE-Reranker Hit@K / Recall@K / MRR；
- 每条 case 的首个正确来源排名变化；
- rerank 平均/P95 延迟；
- reranker 模型 warmup 时间；
- dataset SHA、git SHA、模型路径、collection 等版本指纹。

不会自动把一次运行写成“基线”。只有人工确认数据与环境后显式执行：

```bash
... --write-baseline evals/baselines/erp_wms_retrieval.json
```

后续门禁：

```bash
... \
  --baseline evals/baselines/erp_wms_retrieval.json \
  --regression-tolerance 0.01
```

当前 Hit@K / Recall@K / MRR 任一回退超过 tolerance，脚本返回 exit code 2。

### 5.3 真实 LLM trace + RAGAS

先采集真实 RAG trace：

```bash
uv run --with sentence-transformers --with FlagEmbedding \
  python scripts/capture_rag_eval_traces.py \
  --milvus-url http://localhost:19530 \
  --collection kb_eval_chunks_v1 \
  --embedding-model /models/bge-m3 \
  --reranker-model /models/bge-reranker-large
```

需要配置 `OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL`。该脚本使用真实：

`retrieve -> BGE rerank -> permission filter -> assemble prompt -> LLM`

但故意跳过 FAQ cache 和 record-log 副作用，因此用于模型/检索质量评测，不是在线请求压测。

然后：

```bash
uv run --with ragas==0.4.3 python scripts/evaluate_ragas.py \
  --input evals/results/rag_traces.jsonl
```

只有真实跑出的报告才能写入项目指标。仓库当前不会预置虚构的 Recall@K、MRR 或 RAGAS 数值。
