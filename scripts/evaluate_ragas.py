"""Evaluate captured RAG traces with Ragas 0.4.3.

Input JSONL fields:
  case_id, question, response, reference, retrieved_contexts

Run without adding Ragas to the application's runtime dependencies:
  uv run --with ragas==0.4.3 python scripts/evaluate_ragas.py \
      --input evals/results/rag_traces.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.config.settings import settings

_DEFAULT_OUTPUT = Path("evals/results/ragas_report.csv")
_DEFAULT_BAD_CASES = Path("evals/results/ragas_bad_cases.jsonl")


def _load_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_number}") from exc
            required = {"question", "response", "reference", "retrieved_contexts"}
            missing = required.difference(item)
            if missing:
                raise ValueError(f"missing {sorted(missing)} at {path}:{line_number}")
            rows.append(
                {
                    "case_id": str(item.get("case_id") or f"row-{line_number}"),
                    "user_input": str(item["question"]),
                    "response": str(item["response"]),
                    "reference": str(item["reference"]),
                    "retrieved_contexts": [str(x) for x in item["retrieved_contexts"]],
                }
            )
    return rows


async def _run(args: argparse.Namespace) -> int:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for Ragas LLM-based metrics")

    try:
        from ragas import EvaluationDataset, aevaluate
        from ragas.llms import llm_factory
        from ragas.metrics import (
            ContextPrecision,
            ContextRecall,
            FactualCorrectness,
            Faithfulness,
        )
    except ImportError as exc:
        raise RuntimeError(
            "Ragas is not installed. Run with: uv run --with ragas==0.4.3 "
            "python scripts/evaluate_ragas.py ..."
        ) from exc

    rows = _load_rows(args.input)
    dataset = EvaluationDataset.from_list(
        [
            {
                "user_input": row["user_input"],
                "response": row["response"],
                "reference": row["reference"],
                "retrieved_contexts": row["retrieved_contexts"],
            }
            for row in rows
        ]
    )

    evaluator_llm = llm_factory(
        settings.openai_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
    )
    metrics = [
        ContextPrecision(llm=evaluator_llm),
        ContextRecall(llm=evaluator_llm),
        Faithfulness(llm=evaluator_llm),
        FactualCorrectness(llm=evaluator_llm),
    ]

    result = await aevaluate(
        dataset=dataset,
        metrics=metrics,
        llm=evaluator_llm,
        show_progress=True,
        raise_exceptions=False,
    )
    frame = result.to_pandas()
    frame.insert(0, "case_id", [row["case_id"] for row in rows])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output, index=False)

    metric_thresholds = {
        "context_precision": args.min_context_precision,
        "context_recall": args.min_context_recall,
        "faithfulness": args.min_faithfulness,
        "factual_correctness": args.min_factual_correctness,
    }
    bad_rows: list[dict] = []
    for record in frame.to_dict(orient="records"):
        reasons = []
        for metric, threshold in metric_thresholds.items():
            value = record.get(metric)
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                reasons.append(f"{metric}:invalid")
                continue
            if numeric < threshold:
                reasons.append(f"{metric}:low")
        if reasons:
            bad_rows.append(
                {
                    "case_id": record["case_id"],
                    "question": record.get("user_input"),
                    "reasons": reasons,
                    "scores": {
                        metric: record.get(metric) for metric in metric_thresholds
                    },
                }
            )

    args.bad_cases.parent.mkdir(parents=True, exist_ok=True)
    with args.bad_cases.open("w", encoding="utf-8") as handle:
        for row in bad_rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    summary = {}
    failed_gate = False
    for metric, threshold in metric_thresholds.items():
        mean_value = float(frame[metric].mean())
        summary[metric] = mean_value
        if mean_value < threshold:
            failed_gate = True

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"bad_cases={len(bad_rows)} report={args.output}")
    return 2 if failed_gate else 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate captured RAG traces with Ragas")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--bad-cases", type=Path, default=_DEFAULT_BAD_CASES)
    parser.add_argument("--min-context-precision", type=float, default=0.8)
    parser.add_argument("--min-context-recall", type=float, default=0.8)
    parser.add_argument("--min-faithfulness", type=float, default=0.85)
    parser.add_argument("--min-factual-correctness", type=float, default=0.8)
    return parser.parse_args()


def main() -> None:
    raise SystemExit(asyncio.run(_run(_parse_args())))


if __name__ == "__main__":
    main()
