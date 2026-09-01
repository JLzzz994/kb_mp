"""Run fixed ERP/WMS retrieval evaluation and emit bad-case artifacts.

Usage:
    uv run python scripts/evaluate_retrieval.py
    uv run python scripts/evaluate_retrieval.py --k 5 --disable-query-rewrite

Prerequisite:
    Import the demo knowledge files in 交付物/03-示例数据 into the configured database/Milvus.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.evaluation.retrieval_metrics import (
    aggregate_retrieval_metrics,
    classify_bad_case,
    evaluate_ranked_sources,
)
from app.infrastructure.database import get_session_factory
from app.infrastructure.embedding_factory import build_embedding, build_rerank
from app.infrastructure.llm_factory import build_llm, build_milvus
from app.workflows.context import GraphContext
from app.workflows.nodes.rerank import rerank_node
from app.workflows.nodes.retrieve import retrieve_node
from app.workflows.state import ChatState

_DEFAULT_DATASET = Path("evals/datasets/erp_wms_fixed.jsonl")
_DEFAULT_REPORT = Path("evals/results/retrieval_report.json")
_DEFAULT_BAD_CASES = Path("evals/results/retrieval_bad_cases.jsonl")


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_number}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"expected object at {path}:{line_number}")
            rows.append(value)
    return rows


async def _run(args: argparse.Namespace) -> int:
    cases = _load_jsonl(args.dataset)
    factory = get_session_factory()

    embedding = build_embedding()
    rerank = build_rerank()
    milvus = build_milvus()
    llm = None if args.disable_query_rewrite else build_llm()

    results = []
    bad_cases: list[dict] = []

    async with factory() as session:
        ctx = GraphContext(
            redis=None,  # type: ignore[arg-type]
            session_factory=lambda: session,
            embedding=embedding,
            rerank=rerank,
            milvus=milvus,
            llm=llm,
        )

        for case in cases:
            state: ChatState = {
                "question": str(case["question"]),
                "user_id": 0,
                "history": [],
            }
            state = await retrieve_node(state, ctx)
            state = await rerank_node(state, ctx)
            citations = state.get("reranked_citations") or []

            retrieved_sources = [
                str(item.get("source_file_name") or "")
                for item in citations
                if item.get("source_file_name")
            ]
            top_score = float(citations[0]["score"]) if citations else None
            result = evaluate_ranked_sources(
                case_id=str(case["case_id"]),
                retrieved_sources=retrieved_sources,
                expected_sources=[str(x) for x in case.get("expected_sources", [])],
                k=args.k,
                top_score=top_score,
            )
            results.append(result)

            reasons = classify_bad_case(
                result,
                expected_recall=args.expected_recall,
                max_good_rank=args.max_good_rank,
                min_top_score=args.min_top_score,
            )
            if reasons:
                bad_cases.append(
                    {
                        "case_id": case["case_id"],
                        "question": case["question"],
                        "expected_sources": case.get("expected_sources", []),
                        "retrieved_sources": retrieved_sources,
                        "retrieved": [
                            {
                                "unit_id": item["unit_id"],
                                "chunk_id": item.get("chunk_id"),
                                "source_file_name": item.get("source_file_name"),
                                "section_path": item.get("section_path"),
                                "page_start": item.get("page_start"),
                                "score": item.get("score"),
                            }
                            for item in citations[: args.k]
                        ],
                        "reasons": reasons,
                    }
                )

    summary = aggregate_retrieval_metrics(results)
    report = {
        "dataset": str(args.dataset),
        "k": args.k,
        "thresholds": {
            "expected_recall": args.expected_recall,
            "max_good_rank": args.max_good_rank,
            "min_top_score": args.min_top_score,
        },
        "summary": summary,
        "bad_case_count": len(bad_cases),
        "cases": [item.to_dict() for item in results],
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.bad_cases.parent.mkdir(parents=True, exist_ok=True)
    with args.bad_cases.open("w", encoding="utf-8") as handle:
        for row in bad_cases:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"bad_cases={len(bad_cases)} report={args.report} bad_case_file={args.bad_cases}")

    if (
        float(summary["hit_at_k"]) < args.min_hit_at_k
        or float(summary["recall_at_k"]) < args.min_recall_at_k
        or float(summary["mrr"]) < args.min_mrr
    ):
        return 2
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate ERP/WMS hybrid retrieval")
    parser.add_argument("--dataset", type=Path, default=_DEFAULT_DATASET)
    parser.add_argument("--report", type=Path, default=_DEFAULT_REPORT)
    parser.add_argument("--bad-cases", type=Path, default=_DEFAULT_BAD_CASES)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--expected-recall", type=float, default=1.0)
    parser.add_argument("--max-good-rank", type=int, default=3)
    parser.add_argument("--min-top-score", type=float, default=0.2)
    parser.add_argument("--min-hit-at-k", type=float, default=0.8)
    parser.add_argument("--min-recall-at-k", type=float, default=0.8)
    parser.add_argument("--min-mrr", type=float, default=0.6)
    parser.add_argument("--disable-query-rewrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    raise SystemExit(asyncio.run(_run(_parse_args())))


if __name__ == "__main__":
    main()
