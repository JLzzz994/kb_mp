from __future__ import annotations

from pathlib import Path

from app.evaluation.runtime import (
    compare_metric_summaries,
    compare_named_metrics,
    dataset_sha256,
    load_jsonl,
    model_config_fingerprint,
    runtime_environment_fingerprint,
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


def test_model_config_fingerprint_ignores_weights(tmp_path: Path) -> None:
    model = tmp_path / "model"
    model.mkdir()
    (model / "config.json").write_text('{"hidden_size": 1024}', encoding="utf-8")
    (model / "model.safetensors").write_bytes(b"not-hashed")

    first = model_config_fingerprint(str(model))
    (model / "model.safetensors").write_bytes(b"changed-weight-bytes")
    second = model_config_fingerprint(str(model))

    assert first["exists"] is True
    assert first["metadata_files"] == ["config.json"]
    assert first["metadata_sha256"] == second["metadata_sha256"]
    assert first["weight_file_count"] == 1
    assert first["weight_manifest_sha256"] != second["weight_manifest_sha256"]
    assert "not a full weight-content hash" in first["weight_manifest_note"]


def test_runtime_environment_fingerprint_has_python_and_packages() -> None:
    fingerprint = runtime_environment_fingerprint()
    assert fingerprint["python"]
    assert "platform" in fingerprint
    assert "pymilvus" in fingerprint["packages"]


def test_compare_named_metrics_supports_ragas_metrics() -> None:
    result = compare_named_metrics(
        {
            "context_precision": 0.91,
            "context_recall": 0.79,
            "faithfulness": 0.9,
            "factual_correctness": 0.84,
        },
        {
            "context_precision": 0.9,
            "context_recall": 0.82,
            "faithfulness": 0.9,
            "factual_correctness": 0.85,
        },
        (
            "context_precision",
            "context_recall",
            "faithfulness",
            "factual_correctness",
        ),
        tolerance=0.01,
    )
    assert result["passed"] is False
    assert result["regressions"] == ["context_recall"]
