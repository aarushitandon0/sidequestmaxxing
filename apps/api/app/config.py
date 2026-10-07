"""Settings from environment only (pydantic-settings). Never log values from here."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # .env in the cwd, or the repo-root .env when running from apps/api.
    model_config = SettingsConfigDict(env_file=(".env", "../../.env"), extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    web_origin: str = "http://localhost:5173"
    git_sha: str = "dev"

    # Data
    mongodb_uri: str | None = None
    mongodb_db: str = "sqm"

    # LLM service (llama.cpp). LLM_BASE_URL overrides LLM_HOSTPORT for local dev.
    llm_hostport: str | None = None
    llm_base_url: str | None = None
    llm_model: str = "quest"  # sent as `model`; llama.cpp ignores it, Ollama needs a real tag
    llm_timeout_s: float = Field(default=25.0, gt=0, le=120)
    fallback_on_llm_error: bool = True

    # Voice
    elevenlabs_api_key: str | None = None
    elevenlabs_voice_id: str | None = None
    elevenlabs_model_id: str = "eleven_flash_v2_5"  # low-latency model, 0.5 credits/char
    elevenlabs_output_format: str = "mp3_44100_64"  # ≤128 kbps works on the free tier
    tts_daily_char_budget: int = Field(default=20000, ge=0)
    tts_timeout_s: float = Field(default=10.0, gt=0, le=60)

    # Observability
    sentry_dsn: str | None = None
    sentry_traces_sample_rate: float = Field(default=1.0, ge=0.0, le=1.0)

    # Embeddings
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    @model_validator(mode="after")
    def _fail_fast_in_production(self) -> "Settings":
        if self.env == "production":
            missing = [name for name in ("mongodb_uri",) if not getattr(self, name)]
            if missing:
                raise ValueError(f"missing required env in production: {', '.join(missing)}")
        return self

    @property
    def llm_url(self) -> str | None:
        if self.llm_base_url:
            return self.llm_base_url.rstrip("/")
        if self.llm_hostport:
            return f"http://{self.llm_hostport}"
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
