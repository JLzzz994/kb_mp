"""Reciprocal Rank Fusion for heterogeneous retrieval channels."""

from __future__ import annotations

from collections.abc import Iterable


def reciprocal_rank_fusion(
    ranked_channels: Iterable[list[dict]],
    *,
    rrf_k: int = 60,
    limit: int = 20,
) -> list[dict]:
    """按 unit_id 融合多个有序召回列表，并把 RRF 分数归一化到 0~1。

    RRF 只依赖名次，不直接比较关键词分数和向量相似度，适合混合不同检索通道。
    """
    if rrf_k <= 0:
        raise ValueError("rrf_k must be positive")

    fused_scores: dict[str, float] = {}
    payloads: dict[str, dict] = {}

    for channel in ranked_channels:
        seen_in_channel: set[str] = set()
        for rank, item in enumerate(channel, start=1):
            unit_id = int(item["unit_id"])
            result_key = str(item.get("chunk_id") or f"unit:{unit_id}")
            if result_key in seen_in_channel:
                continue
            seen_in_channel.add(result_key)
            fused_scores[result_key] = fused_scores.get(result_key, 0.0) + 1.0 / (rrf_k + rank)
            payloads.setdefault(result_key, dict(item))

    if not fused_scores:
        return []

    ordered_keys = sorted(fused_scores, key=fused_scores.__getitem__, reverse=True)[:limit]
    max_score = fused_scores[ordered_keys[0]]
    results: list[dict] = []
    for result_key in ordered_keys:
        item = dict(payloads[result_key])
        item["score"] = fused_scores[result_key] / max_score if max_score else 0.0
        results.append(item)
    return results


__all__ = ["reciprocal_rank_fusion"]
