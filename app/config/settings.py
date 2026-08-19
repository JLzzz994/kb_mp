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


settings = Settings()
