from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Options Backtester"
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://trading:trading@postgres:5432/trading"
    chroma_host: str = "chromadb"
    chroma_port: int = 8000
    storage_dir: str = "/app/storage"

    cors_origins: str = "http://localhost:3000"
    default_model: str = "openai:gpt-4o-mini"
    # Optional per-agent overrides (used by the agents in Phase 5); empty = use the request/default model.
    research_model: str = ""
    strategy_model: str = ""
    backtest_model: str = ""
    verify_model: str = ""
    risk_model: str = ""

    # LLM providers: a provider is available only when its key (or Ollama URL) is set.
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    groq_api_key: str = ""
    openrouter_api_key: str = ""
    ollama_base_url: str = ""  # e.g. http://host.docker.internal:11434
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""  # https://<resource>.openai.azure.com
    azure_openai_api_version: str = "2024-12-01-preview"
    azure_openai_deployments: str = ""  # comma-separated deployment names; the model id is azure:<deployment>
    extra_models: str = ""  # comma-separated "provider:model" ids to add to /models
    enable_mock_llm: bool = False  # offline scripted "mock:demo" model for demos/tests; never calls a network

    # Upstox historical data import (Analytics Token needs no daily re-auth; option history needs Upstox Plus)
    upstox_access_token: str = ""

    # Market news for the research agent (public RSS feeds; empty NEWS_FEEDS = built-in list of Indian market sites)
    news_enabled: bool = True
    news_feeds: str = ""  # "Name=https://feed.url,Name2=https://..."
    news_max_age_days: int = 3

    # Auth (email + password, opaque bearer-token sessions stored in the database)
    auth_session_hours: int = 24 * 7
    allow_registration: bool = True

    # Agent pipeline
    agent_timeout_seconds: float = 180.0
    max_concurrent_runs: int = 2

    # RAG
    embedding_provider: str = "fastembed"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    model_cache_dir: str = "/app/.model_cache"
    rag_autoingest: bool = True
    rag_collection: str = "knowledge"

    # Optional tracing: app runs fine when these are empty.
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    @property
    def azure_deployment_list(self) -> list[str]:
        return [d.strip() for d in self.azure_openai_deployments.split(",") if d.strip()]

    @property
    def extra_model_list(self) -> list[str]:
        return [m.strip() for m in self.extra_models.split(",") if m.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
