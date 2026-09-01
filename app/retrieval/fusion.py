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

    fused_scores: dict[int, float] = {}
    payloads: dict[int, dict] = {}

    for channel in ranked_channels:
        seen_in_channel: set[int] = set()
        for rank, item in enumerate(channel, start=1):
            unit_id = int(item["unit_id"])
            if unit_id in seen_in_channel:
                continue
            seen_in_channel.add(unit_id)
            fused_scores[unit_id] = fused_scores.get(unit_id, 0.0) + 1.0 / (rrf_k + rank)
            payloads.setdefault(unit_id, dict(item))

    if not fused_scores:
        return []

    ordered_ids = sorted(fused_scores, key=fused_scores.__getitem__, reverse=True)[:limit]
    max_score = fused_scores[ordered_ids[0]]
    results: list[dict] = []
    for unit_id in ordered_ids:
        item = dict(payloads[unit_id])
        item["score"] = fused_scores[unit_id] / max_score if max_score else 0.0
        results.append(item)
    return results


__all__ = ["reciprocal_rank_fusion"]
