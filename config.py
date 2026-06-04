"""
Application configuration loaded from environment variables.

Uses Pydantic Settings to validate and type-check everything on startup —
the bot fails fast with a clear error if anything is missing or malformed.
"""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime settings, loaded from .env or environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    bot_token: str = Field(..., description="Bot token from @BotFather")
    admin_chat_id: int = Field(..., description="Admin's Telegram user ID")

    # Anthropic
    anthropic_api_key: str = Field(..., description="Anthropic API key")
    claude_model: str = Field(
        default="claude-haiku-4-5",
        description="Claude model name",
    )

    # Company context (used in system prompt)
    company_name: str = Field(default="the company")

    # Knowledge base
    knowledge_dir: Path = Field(default=Path("knowledge"))
    rag_top_k: int = Field(default=3, ge=1, le=10)

    # Conversation
    max_history_turns: int = Field(default=10, ge=1, le=50)
    rate_limit_per_hour: int = Field(default=30, ge=1, le=1000)

    # Storage
    database_path: Path = Field(default=Path("data/bot.db"))

    # Logging
    log_level: str = Field(default="INFO")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid:
            raise ValueError(f"log_level must be one of {valid}, got {v!r}")
        return v_upper


settings = Settings()  # type: ignore[call-arg]
