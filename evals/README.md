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
