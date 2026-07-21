"""
Configuration management using pydantic-settings.

Provides type-safe configuration with validation and startup checks.
All settings are loaded from environment variables and .env file.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # LLM Configuration
    deepseek_api_key: str = Field(..., description="DeepSeek API key")
    llm_model: str = Field(default="deepseek/deepseek-v4-flash", description="LLM model identifier")
    
    # Rate limiting
    max_requests_per_minute: int = Field(default=60, ge=1, le=120, description="Max LLM requests per minute")
    daily_budget_usd: float = Field(default=5.0, ge=0, description="Daily budget in USD")

    # Database Configuration
    cockroachdb_url: str = Field(..., description="CockroachDB connection URL")
    db_pool_minconn: int = Field(default=1, ge=1, le=10, description="Minimum database pool connections")
    db_pool_maxconn: int = Field(default=5, ge=1, le=20, description="Maximum database pool connections")
    db_max_retries: int = Field(default=3, ge=1, le=10, description="Max database connection retries")
    db_retry_delay: float = Field(default=2.0, ge=0.5, le=10.0, description="Delay between DB retries (seconds)")

    # Sentry Configuration
    sentry_dsn: Optional[str] = Field(default="", description="Sentry DSN for error tracking")

    # SMTP Configuration (for email tool)
    smtp_email: Optional[str] = Field(default="", description="SMTP email address")
    smtp_app_password: Optional[str] = Field(default="", description="SMTP app password")
    smtp_server: str = Field(default="smtp.gmail.com", description="SMTP server address")
    smtp_port: int = Field(default=587, ge=1, le=65535, description="SMTP server port")

    # Resume Configuration
    resume_pdf_path: Optional[str] = Field(default="", description="Path to resume PDF file")

    # Tool retry configuration
    tool_max_retries: int = Field(default=2, ge=1, le=5, description="Max retries for failed tool execution")

    # Memory Configuration
    qdrant_url: Optional[str] = Field(default="", description="Qdrant Cloud URL")
    qdrant_api_key: Optional[str] = Field(default="", description="Qdrant Cloud API key")
    qdrant_collection: str = Field(default="agent_memory", description="Qdrant collection name")
    qdrant_vector_size: int = Field(default=4096, description="Embedding vector dimension")
    embedding_provider: str = Field(default="openrouter", description="LiteLLM provider prefix for embeddings (e.g. openrouter, openai, azure)")
    embedding_model: str = Field(default="qwen/qwen3-embedding-8b", description="Embedding model name (e.g. qwen/qwen3-embedding-8b). Combined with embedding_provider for the full LiteLLM model string")
    embedding_api_key: Optional[str] = Field(default="", description="API key for embedding model (OpenRouter key). Falls back to DEEPSEEK_API_KEY if empty")
    top_k_memories: int = Field(default=5, ge=1, le=20, description="Top-K memories to retrieve per query")
    memory_importance_threshold: int = Field(default=6, ge=1, le=10, description="Min importance to persist a memory")

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Returns cached Settings object to avoid re-reading env vars.
    """
    return Settings()


def validate_settings(settings: Settings) -> tuple:
    """
    Validate critical settings and return any issues found.
    
    Args:
        settings: Settings object to validate
        
    Returns:
        Tuple of (is_valid, list_of_warning_messages)
    """
    warnings = []
    
    # Check required fields
    if not settings.deepseek_api_key or settings.deepseek_api_key == "sk-your-deepseek-api-key-here":
        warnings.append("DEEPSEEK_API_KEY is not configured or using placeholder value")
    
    if not settings.cockroachdb_url or settings.cockroachdb_url == "postgresql://your-user:your-password@your-cluster.cockroachlabs.cloud:26257/defaultdb?sslmode=verify-full":
        warnings.append("COCKROACHDB_URL is not configured or using placeholder value")
    
    # Check email configuration if any email field is set
    if settings.smtp_email and not settings.smtp_app_password:
        warnings.append("SMTP_EMAIL is set but SMTP_APP_PASSWORD is missing")
    
    if settings.smtp_app_password and not settings.smtp_email:
        warnings.append("SMTP_APP_PASSWORD is set but SMTP_EMAIL is missing")
    
    # Check resume path if provided
    if settings.resume_pdf_path:
        import os
        if not os.path.isfile(settings.resume_pdf_path):
            warnings.append(f"RESUME_PDF_PATH points to non-existent file: {settings.resume_pdf_path}")
    
    is_valid = len(warnings) == 0
    return is_valid, warnings
