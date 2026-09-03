"""Compare RRF-only vs BGE-Reranker on the same fixed retrieval candidates.

No metric is fabricated. The command requires real BGE-M3, real Milvus and a local
BGE reranker model. A baseline is written only with explicit --write-baseline.

Example:
    uv run --with sentence-transformers --with FlagEmbedding \
      python scripts/compare_retrieval_baseline.py \
      --milvus-url http://localhost:19530 \
      --collection kb_eval_chunks_v1 \
      --embedding-model /models/bge-m3 \
      --reranker-model /models/bge-reranker-large \
      --write-baseline evals/baselines/erp_wms_retrieval.json
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import time
from pathlib import Path
from statistics import fmean

from app.config.settings import settings
from app.evaluation.retrieval_metrics import (
    aggregate_retrieval_metrics,
    classify_bad_case,
    evaluate_ranked_sources,
)
from app.evaluation.runtime import (
    compare_metric_summaries,
    current_git_sha,
    dataset_sha256,
    load_jsonl,
    model_config_fingerprint,
    write_json,
)
from app.infrastructure.database import get_session_factory
from app.infrastructure.embedding_local import LocalBGEEmbedding
from app.infrastructure.llm_factory import build_llm
from app.infrastructure.milvus_gateway import MilvusGateway
from app.infrastructure.rerank_local import LocalBGERerank
from app.workflows.context import GraphContext
from app.workflows.nodes.rerank import rerank_node
from app.workflows.nodes.retrieve import retrieve_node
from app.workflows.state import ChatState

_DEFAULT_DATASET = Path("evals/datasets/erp_wms_fixed.jsonl")
_DEFAULT_OUTPUT = Path("evals/results/retrieval_ab_report.json")


def _sources(citations: list[dict]) -> list[str]:
    return [
        str(item.get("source_file_name") or "")
        for item in citations
        if item.get("source_file_name")
    ]


def _score_case(case: dict, citations: list[dict], k: int):
    return evaluate_ranked_sources(
        case_id=str(case["case_id"]),
        retrieved_sources=_sources(citations),
        expected_sources=[str(x) for x in case.get("expected_sources", [])],
        k=k,
        top_score=float(citations[0]["score"]) if citations else None,
    )


def _variant_payload(results, latencies: list[float], bad_cases: list[dict]) -> dict:
    return {
        "summary": aggregate_retrieval_metrics(results),
        "bad_case_count": len(bad_cases),
        "mean_latency_ms": fmean(latencies) if latencies else 0.0,
        "p95_latency_ms": sorted(latencies)[min(len(latencies) - 1, int(len(latencies) * 0.95))]
        if latencies
        else 0.0,
        "bad_cases": bad_cases,
        "cases": [item.to_dict() for item in results],
    }


async def _run(args: argparse.Namespace) -> int:
    cases = load_jsonl(args.dataset)
    if not cases:
        raise RuntimeError("evaluation dataset is empty")

    embedding = LocalBGEEmbedding(model_path=args.embedding_model, device=args.device)
    probe = await embedding.embed("ERP WMS evaluation probe")
    if len(probe) != settings.embedding_dim:
        raise RuntimeError(
            f"BGE embedding dimension={len(probe)}, expected {settings.embedding_dim}"
        )

    milvus = MilvusGateway(uri=args.milvus_url, collection=args.collection)
    try:
        await milvus.count_by_unit_id(-1)
    except Exception as exc:
        raise RuntimeError("real Milvus evaluation endpoint is unavailable") from exc

    planner_llm = None
    if args.planner_llm:
        planner_llm = build_llm()
        if planner_llm is None:
            raise RuntimeError("--planner-llm requires OPENAI_API_KEY/OPENAI_BASE_URL")
    settings.query_rewrite_enabled = True

    reranker = LocalBGERerank(
        model_path=args.reranker_model,
        device=args.device,
        use_fp16=args.fp16,
    )
    warmup_started = time.perf_counter()
    await reranker.rerank("warmup", ["warmup document"], top_k=1)
    reranker_warmup_ms = (time.perf_counter() - warmup_started) * 1000

    factory = get_session_factory()
    base_ctx = GraphContext(
        redis=None,  # type: ignore[arg-type]
        session_factory=factory,
        embedding=embedding,
        milvus=milvus,
        llm=planner_llm,
        rerank=None,
    )
    rerank_ctx = GraphContext(
        redis=None,  # type: ignore[arg-type]
        session_factory=factory,
        embedding=embedding,
        milvus=milvus,
        llm=planner_llm,
        rerank=reranker,
    )

    base_results = []
    rerank_results = []
    base_bad: list[dict] = []
    rerank_bad: list[dict] = []
    base_latencies: list[float] = []
    rerank_latencies: list[float] = []
    case_comparison: list[dict] = []
    channel_counts: list[dict] = []

    for case in cases:
        state: ChatState = {
            "question": str(case["question"]),
            "user_id": 0,
            "history": [],
        }
        retrieved = await retrieve_node(state, base_ctx)
        counts = dict(retrieved.get("retrieval_channel_counts") or {})
        vector_hits = int(counts.get("vector_rewrite", 0)) + int(counts.get("vector_hyde", 0))
        if vector_hits == 0:
            raise RuntimeError(
                f"{case['case_id']}: vector channels returned zero hits; "
                "refusing to score a lexical/demo fallback as a real BGE baseline"
            )
        channel_counts.append({"case_id": case["case_id"], **counts})

        base_state = copy.deepcopy(retrieved)
        started = time.perf_counter()
        base_state = await rerank_node(base_state, base_ctx)
        base_latencies.append((time.perf_counter() - started) * 1000)
        base_citations = list(base_state.get("reranked_citations") or [])

        rerank_state = copy.deepcopy(retrieved)
        started = time.perf_counter()
        rerank_state = await rerank_node(rerank_state, rerank_ctx)
        rerank_latencies.append((time.perf_counter() - started) * 1000)
        rerank_citations = list(rerank_state.get("reranked_citations") or [])

        base_result = _score_case(case, base_citations, args.k)
        rerank_result = _score_case(case, rerank_citations, args.k)
        base_results.append(base_result)
        rerank_results.append(rerank_result)

        for result, citations, bucket in (
            (base_result, base_citations, base_bad),
            (rerank_result, rerank_citations, rerank_bad),
        ):
            reasons = classify_bad_case(
                result,
                expected_recall=args.expected_recall,
                max_good_rank=args.max_good_rank,
                min_top_score=args.min_top_score,
            )
            if reasons:
                bucket.append(
                    {
                        "case_id": case["case_id"],
                        "question": case["question"],
                        "reasons": reasons,
                        "expected_sources": case.get("expected_sources", []),
                        "retrieved_sources": _sources(citations)[: args.k],
                    }
                )

        case_comparison.append(
            {
                "case_id": case["case_id"],
                "question": case["question"],
                "expected_sources": case.get("expected_sources", []),
                "rrf_first_relevant_rank": base_result.first_relevant_rank,
                "rerank_first_relevant_rank": rerank_result.first_relevant_rank,
                "rrf_sources": _sources(base_citations)[: args.k],
                "rerank_sources": _sources(rerank_citations)[: args.k],
            }
        )

    base_payload = _variant_payload(base_results, base_latencies, base_bad)
    rerank_payload = _variant_payload(rerank_results, rerank_latencies, rerank_bad)
    metric_delta = compare_metric_summaries(
        rerank_payload["summary"],
        base_payload["summary"],
        tolerance=0.0,
    )

    improved = 0
    regressed = 0
    for item in case_comparison:
        before = item["rrf_first_relevant_rank"]
        after = item["rerank_first_relevant_rank"]
        before_rank = int(before) if before is not None else 10**9
        after_rank = int(after) if after is not None else 10**9
        if after_rank < before_rank:
            improved += 1
        elif after_rank > before_rank:
            regressed += 1

    report = {
        "schema_version": 1,
        "git_sha": current_git_sha(),
        "dataset": str(args.dataset),
        "dataset_sha256": dataset_sha256(args.dataset),
        "config": {
            "milvus_url": args.milvus_url,
            "collection": args.collection,
            "embedding_model": model_config_fingerprint(args.embedding_model),
            "embedding_dim": settings.embedding_dim,
            "reranker_model": model_config_fingerprint(args.reranker_model),
            "device": args.device,
            "fp16": args.fp16,
            "planner": "llm" if planner_llm is not None else "deterministic",
            "k": args.k,
            "retrieval_keyword_top_k": settings.retrieval_keyword_top_k,
            "retrieval_vector_top_k": settings.retrieval_vector_top_k,
            "retrieval_rrf_k": settings.retrieval_rrf_k,
            "rerank_top_k": settings.rerank_top_k,
        },
        "reranker_warmup_ms": reranker_warmup_ms,
        "retrieval_channel_counts": channel_counts,
        "rrf_only": base_payload,
        "bge_reranker": rerank_payload,
        "delta_reranker_minus_rrf": {
            **metric_delta["deltas"],
            "improved_case_count": improved,
            "regressed_case_count": regressed,
        },
        "case_comparison": case_comparison,
    }

    baseline_check = None
    if args.baseline:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        expected_sha = str(baseline.get("dataset_sha256") or "")
        if expected_sha and expected_sha != report["dataset_sha256"]:
            raise RuntimeError("baseline dataset SHA differs from current fixed dataset")
        baseline_summary = baseline.get("bge_reranker", {}).get("summary", {})
        baseline_check = compare_metric_summaries(
            rerank_payload["summary"],
            baseline_summary,
            tolerance=args.regression_tolerance,
        )
        report["baseline_check"] = baseline_check

    write_json(args.output, report)
    if args.write_baseline:
        write_json(args.write_baseline, report)

    print(
        json.dumps(
            {
                "rrf_only": base_payload["summary"],
                "bge_reranker": rerank_payload["summary"],
                "delta": report["delta_reranker_minus_rrf"],
                "baseline_check": baseline_check,
                "output": str(args.output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if baseline_check is not None and not baseline_check["passed"]:
        return 2
    if (
        float(rerank_payload["summary"]["hit_at_k"]) < args.min_hit_at_k
        or float(rerank_payload["summary"]["recall_at_k"]) < args.min_recall_at_k
        or float(rerank_payload["summary"]["mrr"]) < args.min_mrr
    ):
        return 2
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare RRF vs real BGE reranking")
    parser.add_argument("--dataset", type=Path, default=_DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--milvus-url", required=True)
    parser.add_argument("--collection", default="kb_eval_chunks_v1")
    parser.add_argument("--embedding-model", required=True)
    parser.add_argument("--reranker-model", required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--fp16", action="store_true")
    parser.add_argument("--planner-llm", action="store_true")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--expected-recall", type=float, default=1.0)
    parser.add_argument("--max-good-rank", type=int, default=3)
    parser.add_argument("--min-top-score", type=float, default=0.2)
    parser.add_argument("--min-hit-at-k", type=float, default=0.8)
    parser.add_argument("--min-recall-at-k", type=float, default=0.8)
    parser.add_argument("--min-mrr", type=float, default=0.6)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--write-baseline", type=Path)
    parser.add_argument("--regression-tolerance", type=float, default=0.0)
    return parser.parse_args()


def main() -> None:
    raise SystemExit(asyncio.run(_run(_parse_args())))


if __name__ == "__main__":
    main()
