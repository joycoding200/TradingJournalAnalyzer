import os
import re
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


# ── Known-weak key patterns ──────────────────────────────────────────
# In production, a secret_key matching any of these is rejected even if
# length ≥ 32. Covers common developer placeholder patterns that would
# otherwise pass a naive length check.  See review P1-11, P1-13.
_WEAK_KEY_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"^dev[\-_]",
        r"[\-_]dev[\-_]",
        r"[\-_]dev$",
        r"^test[\-_]",
        r"[\-_]test[\-_]",
        r"[\-_]test$",
        r"^change[\-_]?me",
        r"^secret[\-_]?key",
        r"^default[\-_]",
        r"^changeme$",
        r"^foobar$",
        r"^12345678",
        r"^password",
        r"^admin[\-_]?",
    ]
]


class Settings(BaseSettings):
    database_url: str = "postgresql://localhost:5432/tradelens"
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_audience: str = "tja-api"
    jwt_expire_minutes: int = 480  # 8 hours — avoids silent expiration during use
    ai_provider: str = "openai"  # openai | claude | deepseek | openrouter
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    claude_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    cors_origins: str = "http://localhost:5173"
    ai_base_url: str = Field(default="", alias="BASE_URL")
    ai_model: str = Field(default="", alias="MODEL")
    env: str = Field(default="development", alias="ENV")

    @property
    def is_production(self) -> bool:
        return self.env.lower() in ("prod", "production")

    @property
    def cookie_secure(self) -> bool:
        """Derive cookie secure flag from ENV. True in production, False otherwise."""
        return self.is_production

    model_config = {
        "env_file": str(Path(__file__).resolve().parent.parent / ".env"),
        "populate_by_name": True,
    }

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        env = os.getenv("ENV", "development")
        is_production = env.lower() in ["prod", "production"]

        if is_production:
            if v == "change-me-in-production":
                raise RuntimeError(
                    "In production, secret_key must be set via environment variable, "
                    "not the default value"
                )
            if len(v) < 32:
                raise RuntimeError(
                    "In production, secret_key must be at least 32 characters long"
                )
            # P1-11, P1-13: reject known-weak key patterns
            for pattern in _WEAK_KEY_PATTERNS:
                if pattern.search(v):
                    raise RuntimeError(
                        f"In production, secret_key matches a known-weak pattern. "
                        f"Generate a strong random key: openssl rand -hex 32"
                    )
            # Require at least 2 of {uppercase, digit, special} for minimal entropy
            classes = 0
            if re.search(r"[A-Z]", v):
                classes += 1
            if re.search(r"\d", v):
                classes += 1
            if re.search(r"[^A-Za-z0-9]", v):
                classes += 1
            if classes < 2:
                raise RuntimeError(
                    "In production, secret_key must contain at least 2 of: "
                    "uppercase letters, digits, special characters"
                )

        return v


settings = Settings()
