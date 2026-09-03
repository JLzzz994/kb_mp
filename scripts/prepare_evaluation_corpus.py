"""Prepare the fixed ERP/WMS evaluation corpus in MySQL + real Milvus.

This command is intentionally fail-fast: it requires a real BGE-M3 model path and a
reachable Milvus endpoint. It never falls back to demo citations.

Example:
    uv run --with sentence-transformers python scripts/prepare_evaluation_corpus.py \
      --milvus-url http://localhost:19530 \
      --collection kb_eval_chunks_v1 \
      --embedding-model /models/bge-m3
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.config.settings import settings
from app.evaluation.runtime import (
    dataset_sha256,
    load_jsonl,
    model_config_fingerprint,
    write_json,
)
from app.infrastructure.database import KnowledgeUnitRecord, UserRecord, get_session_factory
from app.infrastructure.embedding_local import LocalBGEEmbedding
from app.infrastructure.milvus_gateway import MilvusGateway
from app.repositories.knowledge_unit_repository import UnitPermissionRepository
from app.services.knowledge_import_service import KnowledgeImportService
from app.services.knowledge_index_service import KnowledgeIndexService

_DEFAULT_DATASET = Path("evals/datasets/erp_wms_fixed.jsonl")
_DEFAULT_SOURCE_DIR = Path("交付物/03-示例数据")
_DEFAULT_OUTPUT = Path("evals/results/corpus_prepare_report.json")


async def _probe_vector_stack(
    embedding: LocalBGEEmbedding,
    milvus: MilvusGateway,
) -> int:
    vector = await embedding.embed("ERP WMS evaluation dimension probe")
    dimension = len(vector)
    if dimension != settings.embedding_dim:
        raise RuntimeError(
            f"BGE embedding dimension={dimension}, but EMBEDDING_DIM={settings.embedding_dim}"
        )
    try:
        await milvus.count_by_unit_id(-1)
    except Exception as exc:
        raise RuntimeError("Milvus evaluation endpoint is not reachable/usable") from exc
    return dimension


async def _resolve_creator_id(session, requested: int | None) -> int:
    if requested is not None:
        exists = await session.scalar(select(UserRecord.id).where(UserRecord.id == requested))
        if exists is None:
            raise RuntimeError(f"creator user id={requested} does not exist; run scripts/seed.py")
        return int(exists)

    first = await session.scalar(select(UserRecord.id).order_by(UserRecord.id).limit(1))
    if first is None:
        raise RuntimeError("no user exists; run scripts/seed.py before preparing evaluation corpus")
    return int(first)


async def _run(args: argparse.Namespace) -> int:
    cases = load_jsonl(args.dataset)
    expected_sources = sorted(
        {
            str(source)
            for case in cases
            for source in case.get("expected_sources", [])
            if str(source)
        }
    )
    if not expected_sources:
        raise RuntimeError("evaluation dataset has no expected_sources")

    missing_files = [name for name in expected_sources if not (args.source_dir / name).is_file()]
    if missing_files:
        raise RuntimeError(f"evaluation source files missing: {missing_files}")

    embedding = LocalBGEEmbedding(model_path=args.embedding_model, device=args.device)
    milvus = MilvusGateway(uri=args.milvus_url, collection=args.collection)
    dimension = await _probe_vector_stack(embedding, milvus)

    factory = get_session_factory()
    imported: list[str] = []
    indexed: list[dict] = []

    async with factory() as session:
        creator_id = await _resolve_creator_id(session, args.creator_id)

        rows = list(
            (
                await session.execute(
                    select(KnowledgeUnitRecord).where(
                        KnowledgeUnitRecord.source_file_name.in_(expected_sources)
                    )
                )
            )
            .scalars()
            .all()
        )
        existing = {str(row.source_file_name): row for row in rows if row.source_file_name}

        missing_sources = [name for name in expected_sources if name not in existing]
        if missing_sources:
            importer = KnowledgeImportService(session)
            response = await importer.import_files(
                files=[(name, (args.source_dir / name).read_bytes()) for name in missing_sources],
                user_id=creator_id,
            )
            if response.rejected:
                raise RuntimeError(
                    "evaluation corpus import rejected files: "
                    + json.dumps(
                        [item.model_dump() for item in response.rejected],
                        ensure_ascii=False,
                    )
                )
            imported.extend(missing_sources)

        rows = list(
            (
                await session.execute(
                    select(KnowledgeUnitRecord).where(
                        KnowledgeUnitRecord.source_file_name.in_(expected_sources)
                    )
                )
            )
            .scalars()
            .all()
        )
        by_source = {str(row.source_file_name): row for row in rows if row.source_file_name}
        still_missing = [name for name in expected_sources if name not in by_source]
        if still_missing:
            raise RuntimeError(f"corpus rows still missing after import: {still_missing}")

        permission_repo = UnitPermissionRepository(session)
        index_service = KnowledgeIndexService(
            session,
            embedding=embedding,
            milvus=milvus,
        )
        for source_name in expected_sources:
            record = by_source[source_name]
            await permission_repo.replace_all(record.id, [("global", None)])
            await session.commit()
            status = await index_service.rebuild_unit(record.id, prefer_source=True)
            indexed.append(
                {
                    "source_file_name": source_name,
                    "unit_id": record.id,
                    "unit_code": record.unit_code,
                    "chunk_count": status.chunk_count,
                    "consistent": status.consistent,
                }
            )

    report = {
        "dataset": str(args.dataset),
        "dataset_sha256": dataset_sha256(args.dataset),
        "source_dir": str(args.source_dir),
        "milvus_url": args.milvus_url,
        "collection": args.collection,
        "embedding_model": model_config_fingerprint(args.embedding_model),
        "embedding_dim": dimension,
        "imported_sources": imported,
        "expected_sources": expected_sources,
        "indexed": indexed,
    }
    write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare real ERP/WMS evaluation corpus")
    parser.add_argument("--dataset", type=Path, default=_DEFAULT_DATASET)
    parser.add_argument("--source-dir", type=Path, default=_DEFAULT_SOURCE_DIR)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--milvus-url", required=True)
    parser.add_argument("--collection", default="kb_eval_chunks_v1")
    parser.add_argument("--embedding-model", required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--creator-id", type=int)
    return parser.parse_args()


def main() -> None:
    raise SystemExit(asyncio.run(_run(_parse_args())))


if __name__ == "__main__":
    main()
