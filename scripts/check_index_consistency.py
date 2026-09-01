"""Audit MySQL knowledge units against Milvus chunk index.

Examples:
    uv run python scripts/check_index_consistency.py
    uv run python scripts/check_index_consistency.py --repair
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.infrastructure.database import KnowledgeUnitRecord, get_session_factory
from app.infrastructure.embedding_factory import build_embedding
from app.infrastructure.llm_factory import build_milvus
from app.services.knowledge_index_service import KnowledgeIndexService

_DEFAULT_OUTPUT = Path("reports/index-consistency.json")


async def _run(args: argparse.Namespace) -> int:
    milvus = build_milvus()
    if milvus is None:
        print("Milvus is disabled; index consistency cannot be verified.")
        return 2

    embedding = None
    if args.repair:
        embedding = build_embedding()

    factory = get_session_factory()
    async with factory() as session:
        rows = list(
            (
                await session.execute(
                    select(KnowledgeUnitRecord).order_by(KnowledgeUnitRecord.id).limit(args.limit)
                )
            )
            .scalars()
            .all()
        )
        service = KnowledgeIndexService(
            session,
            embedding=embedding,
            milvus=milvus,
        )

        results: list[dict] = []
        repaired: list[int] = []
        for record in rows:
            status = await service.get_status(record.id)
            if args.repair and not status.consistent:
                status = await service.rebuild_unit(record.id)
                repaired.append(record.id)
            results.append(
                {
                    "unit_id": status.unit_id,
                    "unit_code": record.unit_code,
                    "title": record.title,
                    "db_status": status.db_status,
                    "chunk_count": status.chunk_count,
                    "consistent": status.consistent,
                    "detail": status.detail,
                }
            )

    inconsistent = [row for row in results if not row["consistent"]]
    report = {
        "checked": len(results),
        "healthy": len(results) - len(inconsistent),
        "inconsistent": len(inconsistent),
        "repaired_unit_ids": repaired,
        "items": results,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "checked": report["checked"],
                "healthy": report["healthy"],
                "inconsistent": report["inconsistent"],
                "repaired_unit_ids": repaired,
                "report": str(args.output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 2 if inconsistent else 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit knowledge-unit vector index consistency")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--repair", action="store_true")
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    raise SystemExit(asyncio.run(_run(_parse_args())))


if __name__ == "__main__":
    main()
