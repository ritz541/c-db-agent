from functools import lru_cache
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM Configuration
    deepseek_api_key: str = Field(default="", description="DeepSeek API key")
    llm_model: str = Field(
        default="deepseek/deepseek-v4-flash", description="LLM model identifier"
    )

    # Rate limiting
    max_requests_per_minute: int = Field(
        default=60, ge=1, le=120, description="Max LLM requests per minute"
    )
    daily_budget_usd: float = Field(
        default=5.0, ge=0, description="Daily budget in USD"
    )

    # Database Configuration
    cockroachdb_url: str = Field(default="", description="CockroachDB connection URL")
    db_pool_minconn: int = Field(
        default=1, ge=1, le=10, description="Minimum database pool connections"
    )
    db_pool_maxconn: int = Field(
        default=5, ge=1, le=20, description="Maximum database pool connections"
    )
    db_max_retries: int = Field(
        default=3, ge=1, le=10, description="Max database connection retries"
    )
    db_retry_delay: float = Field(
        default=2.0, ge=0.5, le=10.0, description="Delay between DB retries (seconds)"
    )

    # Sentry Configuration
    sentry_dsn: Optional[str] = Field(
        default="", description="Sentry DSN for error tracking"
    )

    # SMTP Configuration (for email tool)
    smtp_email: Optional[str] = Field(default="", description="SMTP email address")
    smtp_app_password: Optional[str] = Field(
        default="", description="SMTP app password"
    )
    smtp_server: str = Field(
        default="smtp.gmail.com", description="SMTP server address"
    )
    smtp_port: int = Field(
        default=587, ge=1, le=65535, description="SMTP server port"
    )

    # Resume Configuration
    resume_pdf_path: Optional[str] = Field(
        default="", description="Path to resume PDF file"
    )

    # Tool retry configuration
    tool_max_retries: int = Field(
        default=2, ge=1, le=5, description="Max retries for failed tool execution"
    )

    # Memory Configuration
    qdrant_url: Optional[str] = Field(default="", description="Qdrant Cloud URL")
    qdrant_api_key: Optional[str] = Field(
        default="", description="Qdrant Cloud API key"
    )
    qdrant_collection: str = Field(
        default="agent_memory", description="Qdrant collection name"
    )
    qdrant_vector_size: int = Field(
        default=4096, description="Embedding vector dimension"
    )
    embedding_provider: str = Field(
        default="openrouter",
        description="LiteLLM provider prefix for embeddings",
    )
    embedding_model: str = Field(
        default="qwen/qwen3-embedding-8b", description="Embedding model name"
    )
    embedding_api_key: Optional[str] = Field(
        default="", description="API key for embedding model"
    )
    top_k_memories: int = Field(
        default=5, ge=1, le=20, description="Top-K memories to retrieve per query"
    )
    memory_importance_threshold: int = Field(
        default=6, ge=1, le=10, description="Min importance to persist a memory"
    )

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


def validate_settings(settings: Settings) -> tuple[bool, list[str]]:
    warnings = []
    is_valid = True
    if not settings.deepseek_api_key:
        warnings.append("DEEPSEEK_API_KEY is not set.")
    if not settings.cockroachdb_url:
        warnings.append("COCKROACHDB_URL is not set.")
    return is_valid, warnings
