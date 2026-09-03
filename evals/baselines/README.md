# Real evaluation baselines

这里仅保存**真实环境执行并人工确认过**的评测基线。

当前支持两类基线：

- `erp_wms_retrieval.json`：Hit@K / Recall@K / MRR；
- `erp_wms_ragas.json`：Context Precision / Recall、Faithfulness、Factual Correctness。

不要手工编造或根据简历目标反推指标。推荐流程：

1. 运行 `scripts/prepare_evaluation_corpus.py` 准备固定 ERP/WMS 语料；
2. 运行 `scripts/compare_retrieval_baseline.py` 查看 RRF vs BGE-Reranker A/B；
3. 核对 dataset SHA、git SHA、模型路径/版本、Milvus collection；
4. 结果可信后再次执行并显式传入：

```bash
--write-baseline evals/baselines/erp_wms_retrieval.json
```

5. 后续版本使用 `--baseline` 做回归比较。

RAGAS 基线同样必须从真实 `rag_traces.jsonl` 执行后显式写入，不能手工填指标。

提交前至少检查：

- dataset SHA 与固定集一致；
- git SHA 可追溯；
- BGE / reranker 模型指纹与运行环境记录完整；
- 报告没有混入业务敏感数据；
- 指标来自实际命令输出，不是根据简历目标反推。

仓库没有基线 JSON 时，含义是“尚未产生可验证的真实指标”，不是测试失败。
