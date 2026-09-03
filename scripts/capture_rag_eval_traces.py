"""Capture real RAG traces for Ragas from the fixed ERP/WMS dataset.

This intentionally bypasses FAQ cache and record-log side effects, but uses the real
retrieve -> BGE rerank -> permission filter -> prompt -> LLM generation path.
Evaluation corpus sources should be global via prepare_evaluation_corpus.py.

Example:
    uv run --with sentence-transformers --with FlagEmbedding \
      python scripts/capture_rag_eval_traces.py \
      --milvus-url http://localhost:19530 \
      --collection kb_eval_chunks_v1 \
      --embedding-model /models/bge-m3 \
      --reranker-model /models/bge-reranker-large
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.config.settings import settings
from app.evaluation.runtime import load_jsonl
from app.infrastructure.database import get_session_factory
from app.infrastructure.embedding_local import LocalBGEEmbedding
from app.infrastructure.llm_factory import build_llm
from app.infrastructure.milvus_gateway import MilvusGateway
from app.infrastructure.rerank_local import LocalBGERerank
from app.workflows.context import GraphContext
from app.workflows.nodes.assemble_prompt import assemble_prompt_node
from app.workflows.nodes.generate import generate_node
from app.workflows.nodes.permission_filter import permission_filter_node
from app.workflows.nodes.rerank import rerank_node
from app.workflows.nodes.retrieve import retrieve_node
from app.workflows.state import ChatState

_DEFAULT_DATASET = Path("evals/datasets/erp_wms_fixed.jsonl")
_DEFAULT_OUTPUT = Path("evals/results/rag_traces.jsonl")


async def _run(args: argparse.Namespace) -> int:
    llm = build_llm()
    if llm is None:
        raise RuntimeError(
            "real RAG trace capture requires OPENAI_API_KEY and an OpenAI-compatible LLM"
        )

    embedding = LocalBGEEmbedding(model_path=args.embedding_model, device=args.device)
    probe = await embedding.embed("ERP WMS RAG trace probe")
    if len(probe) != settings.embedding_dim:
        raise RuntimeError(
            f"BGE embedding dimension={len(probe)}, expected {settings.embedding_dim}"
        )

    milvus = MilvusGateway(uri=args.milvus_url, collection=args.collection)
    try:
        await milvus.count_by_unit_id(-1)
    except Exception as exc:
        raise RuntimeError("real Milvus evaluation endpoint is unavailable") from exc

    reranker = LocalBGERerank(
        model_path=args.reranker_model,
        device=args.device,
        use_fp16=args.fp16,
    )
    await reranker.rerank("warmup", ["warmup document"], top_k=1)

    factory = get_session_factory()
    retrieval_ctx = GraphContext(
        redis=None,  # type: ignore[arg-type]
        session_factory=factory,
        embedding=embedding,
        milvus=milvus,
        llm=None if args.disable_planner_llm else llm,
        rerank=reranker,
    )
    generation_ctx = GraphContext(
        redis=None,  # type: ignore[arg-type]
        session_factory=factory,
        embedding=embedding,
        milvus=milvus,
        llm=llm,
        rerank=reranker,
    )

    rows: list[dict] = []
    for case in load_jsonl(args.dataset):
        state: ChatState = {
            "question": str(case["question"]),
            "user_id": args.user_id,
            "user_dept_ids": [],
            "user_role_ids": [],
            "user_permissions": [],
            "history": [],
        }
        state = await retrieve_node(state, retrieval_ctx)
        counts = state.get("retrieval_channel_counts") or {}
        if int(counts.get("vector_rewrite", 0)) + int(counts.get("vector_hyde", 0)) == 0:
            raise RuntimeError(
                f"{case['case_id']}: zero vector hits; refusing to capture fallback trace"
            )
        state = await rerank_node(state, retrieval_ctx)
        state = await permission_filter_node(state, retrieval_ctx)
        citations = list(state.get("authorized_citations") or [])
        if not citations:
            raise RuntimeError(
                f"{case['case_id']}: no authorized citations; "
                "prepare evaluation corpus with global permissions first"
            )
        state = await assemble_prompt_node(state, generation_ctx)
        state = await generate_node(state, generation_ctx)

        rows.append(
            {
                "case_id": str(case["case_id"]),
                "question": str(case["question"]),
                "response": state.get("answer", ""),
                "reference": str(case.get("reference") or ""),
                "retrieved_contexts": [
                    f"{item.get('title', '')}\n{item.get('content', '')}"
                    for item in citations
                ],
                "retrieved_sources": [
                    item.get("source_file_name")
                    for item in citations
                    if item.get("source_file_name")
                ],
                "prompt_tokens": state.get("prompt_tokens", 0),
                "completion_tokens": state.get("completion_tokens", 0),
                "total_tokens": state.get("total_tokens", 0),
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"captured={len(rows)} output={args.output}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture real ERP/WMS RAG traces")
    parser.add_argument("--dataset", type=Path, default=_DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--milvus-url", required=True)
    parser.add_argument("--collection", default="kb_eval_chunks_v1")
    parser.add_argument("--embedding-model", required=True)
    parser.add_argument("--reranker-model", required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--fp16", action="store_true")
    parser.add_argument("--disable-planner-llm", action="store_true")
    parser.add_argument("--user-id", type=int, default=1)
    return parser.parse_args()


def main() -> None:
    raise SystemExit(asyncio.run(_run(_parse_args())))


if __name__ == "__main__":
    main()
