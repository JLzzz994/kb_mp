"""Deterministic retrieval metrics and bad-case classification."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import fmean


@dataclass(frozen=True, slots=True)
class RetrievalCaseResult:
    case_id: str
    hit_at_k: float
    recall_at_k: float
    reciprocal_rank: float
    first_relevant_rank: int | None
    retrieved_count: int
    expected_count: int
    top_score: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def evaluate_ranked_sources(
    *,
    case_id: str,
    retrieved_sources: list[str],
    expected_sources: list[str],
    k: int = 5,
    top_score: float | None = None,
) -> RetrievalCaseResult:
    """Score source-file retrieval without depending on unstable database IDs."""
    ranked = _dedupe(retrieved_sources)
    expected = set(_dedupe(expected_sources))
    cutoff = ranked[: max(k, 1)]

    relevant_in_cutoff = expected.intersection(cutoff)
    recall = len(relevant_in_cutoff) / len(expected) if expected else 1.0
    first_rank: int | None = None
    for index, source in enumerate(ranked, start=1):
        if source in expected:
            first_rank = index
            break

    return RetrievalCaseResult(
        case_id=case_id,
        hit_at_k=1.0 if relevant_in_cutoff else 0.0,
        recall_at_k=recall,
        reciprocal_rank=1.0 / first_rank if first_rank else 0.0,
        first_relevant_rank=first_rank,
        retrieved_count=len(ranked),
        expected_count=len(expected),
        top_score=top_score,
    )


def classify_bad_case(
    result: RetrievalCaseResult,
    *,
    expected_recall: float = 1.0,
    max_good_rank: int = 3,
    min_top_score: float = 0.2,
) -> list[str]:
    """Return stable reason codes used by bad-case review workflows."""
    reasons: list[str] = []
    if result.retrieved_count == 0:
        reasons.append("no_recall")
        return reasons
    if result.recall_at_k < expected_recall:
        reasons.append("source_miss")
    if result.first_relevant_rank is None:
        reasons.append("no_relevant_source")
    elif result.first_relevant_rank > max_good_rank:
        reasons.append("low_rank")
    if result.top_score is not None and result.top_score < min_top_score:
        reasons.append("low_confidence")
    return reasons


def aggregate_retrieval_metrics(results: list[RetrievalCaseResult]) -> dict[str, float | int]:
    if not results:
        return {
            "case_count": 0,
            "hit_at_k": 0.0,
            "recall_at_k": 0.0,
            "mrr": 0.0,
        }
    return {
        "case_count": len(results),
        "hit_at_k": fmean(item.hit_at_k for item in results),
        "recall_at_k": fmean(item.recall_at_k for item in results),
        "mrr": fmean(item.reciprocal_rank for item in results),
    }


__all__ = [
    "RetrievalCaseResult",
    "aggregate_retrieval_metrics",
    "classify_bad_case",
    "evaluate_ranked_sources",
]
