from __future__ import annotations

from pathlib import Path

from app.evaluation.runtime import (
    compare_metric_summaries,
    dataset_sha256,
    load_jsonl,
)


def test_compare_metric_summaries_detects_regression() -> None:
    result = compare_metric_summaries(
        {"hit_at_k": 0.9, "recall_at_k": 0.78, "mrr": 0.7},
        {"hit_at_k": 0.9, "recall_at_k": 0.8, "mrr": 0.75},
        tolerance=0.01,
    )
    assert result["passed"] is False
    assert result["regressions"] == ["recall_at_k", "mrr"]


def test_compare_metric_summaries_allows_tolerance() -> None:
    result = compare_metric_summaries(
        {"hit_at_k": 0.895, "recall_at_k": 0.795, "mrr": 0.745},
        {"hit_at_k": 0.9, "recall_at_k": 0.8, "mrr": 0.75},
        tolerance=0.01,
    )
    assert result["passed"] is True
    assert result["regressions"] == []


def test_load_jsonl_and_dataset_sha(tmp_path: Path) -> None:
    path = tmp_path / "dataset.jsonl"
    path.write_text(
        '{"case_id":"a","question":"q"}\n{"case_id":"b","question":"q2"}\n',
        encoding="utf-8",
    )
    rows = load_jsonl(path)
    assert [row["case_id"] for row in rows] == ["a", "b"]
    assert len(dataset_sha256(path)) == 64
