"""Helpers for reproducible ERP/WMS evaluation runs."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
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
            if not isinstance(item, dict):
                raise ValueError(f"expected object at {path}:{line_number}")
            rows.append(item)
    return rows


def dataset_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_git_sha() -> str:
    env_sha = os.getenv("GITHUB_SHA", "").strip()
    if env_sha:
        return env_sha
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def compare_metric_summaries(
    current: dict[str, float | int],
    baseline: dict[str, float | int],
    *,
    tolerance: float = 0.0,
) -> dict:
    metrics = ("hit_at_k", "recall_at_k", "mrr")
    deltas: dict[str, float] = {}
    regressions: list[str] = []
    for metric in metrics:
        current_value = float(current.get(metric, 0.0))
        baseline_value = float(baseline.get(metric, 0.0))
        delta = current_value - baseline_value
        deltas[metric] = delta
        if delta < -abs(tolerance):
            regressions.append(metric)
    return {
        "tolerance": abs(tolerance),
        "deltas": deltas,
        "regressions": regressions,
        "passed": not regressions,
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


__all__ = [
    "compare_metric_summaries",
    "current_git_sha",
    "dataset_sha256",
    "load_jsonl",
    "write_json",
]
