"""
Configuration management using pydantic-settings.

This module provides type-safe configuration with validation.
All settings are loaded from environment variables and .env file.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # LLM Configuration
    deepseek_api_key: str
    llm_model: str = "deepseek/deepseek-v4-flash"

    # Database Configuration
    cockroachdb_url: str

    # Sentry Configuration
    sentry_dsn: str = ""

    # SMTP Configuration (for email tool)
    smtp_email: str = ""
    smtp_app_password: str = ""
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587

    # Resume Configuration
    resume_pdf_path: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Returns cached Settings object to avoid re-reading env vars.
    """
    return Settings()
