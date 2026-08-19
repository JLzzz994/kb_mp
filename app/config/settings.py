"""应用全局配置（Pydantic Settings）。字段从 .env 读取，敏感字段不入库。"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """kb_mp 全局配置。

    - 锁定决策见 docs/CONTEXT.md Q1-Q8 与 docs/adr/0003。
    - JWT / bcrypt / Redis 字段在 PR0 阶段补齐，P0 业务模块直接复用。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── 应用 ─────────────────────────────
    app_name: str = "kb-mp"
    debug: bool = False
    log_level: str = "INFO"

    # ── 数据库 ─────────────────────────────
    database_url: str = "mysql+aiomysql://user:pass@localhost:3306/kb_mp"

    # ── Redis ─────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    auth_bitmap_ttl_seconds: int = 300  # 鉴权位图 TTL（5 分钟）

    # ── JWT（锁定决策 Q1） ─────────────────────────────
    jwt_secret: str = "kb-mp-demo-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480  # 8 小时

    # ── bcrypt（锁定决策 Q2） ─────────────────────────────
    bcrypt_cost: int = 12

    # ── LLM / Embedding（M3 / M4 使用） ─────────────────────────────
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    # ── Milvus（M3 使用） ─────────────────────────────
    milvus_host: str = "localhost"
    milvus_port: int = 19530

    # ── 文件存储（M3 使用） ─────────────────────────────
    storage_dir: str = "./storage/uploads"
    max_upload_size_mb: int = 20
    max_total_upload_size_mb: int = 200

    # ── Embedding 后端（本地 / 远程） ─────────────────────────────
    # "local_bge"           → 本地 BGE-M3（魔搭下载）
    # "remote_openai"        → 远程 OpenAI 兼容 API（如 DashScope）
    embedding_backend: str = "local_bge"
    bge_m3_path: str = "D:/ai_models/modelscope_cache/models/BAAI/bge-m3"
    bge_m3_name: str = "BAAI/bge-m3"
    bge_device: str = "cpu"
    bge_fp16: bool = False
    bge_use_fp16: bool = False
    embedding_dim: int = 1024

    # ── Rerank 后端 ─────────────────────────────
    # "disabled" | "local_bge"
    rerank_backend: str = "disabled"
    bge_reranker_path: str = "D:/ai_models/modelscope_cache/models/rerank/BAAI/bge-reranker-large"
    bge_reranker_device: str = "cpu"
    bge_reranker_fp16: bool = False

    # ── Milvus 远程服务 ─────────────────────────────
    # 演示期 mock；生产期指向远程 Milvus（兼容 docker / 独立部署）
    milvus_url: str = "http://39.105.7.90:19530"
    milvus_collection: str = "kb_units"
    milvus_index_metric: str = "COSINE"
    milvus_index_m: int = 16
    milvus_index_ef_construction: int = 64


settings = Settings()
