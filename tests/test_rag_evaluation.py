from app.evaluation.retrieval_metrics import (
    aggregate_retrieval_metrics,
    classify_bad_case,
    evaluate_ranked_sources,
)


def test_retrieval_metrics_hit_recall_and_mrr() -> None:
    result = evaluate_ranked_sources(
        case_id="c1",
        retrieved_sources=["noise.md", "inventory.md", "other.md"],
        expected_sources=["inventory.md"],
        k=3,
        top_score=0.91,
    )
    assert result.hit_at_k == 1.0
    assert result.recall_at_k == 1.0
    assert result.first_relevant_rank == 2
    assert result.reciprocal_rank == 0.5
    assert classify_bad_case(result) == []


def test_cross_domain_recall_detects_partial_source_miss() -> None:
    result = evaluate_ranked_sources(
        case_id="cross",
        retrieved_sources=["aftersales.md", "noise.md"],
        expected_sources=["aftersales.md", "inventory.md"],
        k=5,
        top_score=0.8,
    )
    assert result.hit_at_k == 1.0
    assert result.recall_at_k == 0.5
    assert "source_miss" in classify_bad_case(result)


def test_bad_case_classifies_no_recall() -> None:
    result = evaluate_ranked_sources(
        case_id="empty",
        retrieved_sources=[],
        expected_sources=["expected.md"],
        k=5,
    )
    assert classify_bad_case(result) == ["no_recall"]


def test_bad_case_classifies_low_rank_and_confidence() -> None:
    result = evaluate_ranked_sources(
        case_id="low",
        retrieved_sources=["1", "2", "3", "expected"],
        expected_sources=["expected"],
        k=5,
        top_score=0.1,
    )
    reasons = classify_bad_case(result, max_good_rank=3, min_top_score=0.2)
    assert "low_rank" in reasons
    assert "low_confidence" in reasons


def test_aggregate_retrieval_metrics() -> None:
    a = evaluate_ranked_sources(
        case_id="a",
        retrieved_sources=["a.md"],
        expected_sources=["a.md"],
        k=5,
    )
    b = evaluate_ranked_sources(
        case_id="b",
        retrieved_sources=["noise.md"],
        expected_sources=["b.md"],
        k=5,
    )
    summary = aggregate_retrieval_metrics([a, b])
    assert summary["case_count"] == 2
    assert summary["hit_at_k"] == 0.5
    assert summary["recall_at_k"] == 0.5
    assert summary["mrr"] == 0.5
