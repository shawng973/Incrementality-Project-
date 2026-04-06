from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    database_url: str = ""

    # JWT
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"

    # Redis / ARQ
    redis_url: str = "redis://localhost:6379"

    # LLM — OpenRouter (model is hot-swappable via LLM_MODEL env var)
    openrouter_api_key: str = ""
    llm_model: str = "anthropic/claude-sonnet-4-5"
    llm_site_url: str = "https://incremental-tool.terroir.com"
    llm_site_name: str = "Incremental Tool"

    # App
    environment: str = "development"
    log_level: str = "INFO"
    # Comma-separated list of allowed CORS origins (in addition to localhost:3000)
    cors_origins: str = ""


settings = Settings()
