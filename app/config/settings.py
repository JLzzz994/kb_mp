from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用全局配置，从 .env 读取，敏感字段不入库。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "kb-mp"
    debug: bool = False
    log_level: str = "INFO"

    database_url: str = "mysql+aiomysql://user:pass@localhost:3306/kb_mp"

    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o-mini"


settings = Settings()
