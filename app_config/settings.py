from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Gemma test harness settings — loaded from .env"""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    # ── vLLM inference server ──────────────────────────────────────────────
    # Points at the vLLM OpenAI-compatible endpoint running on the pod.
    # Override via .env or SSH tunnel forwarding.
    VLLM_BASE_URL: str = "http://localhost:8002"
    VLLM_MODEL_NAME: str = "gemma4-26b-it"
    VLLM_API_KEY: Optional[str] = None
    # vLLM 0.19+ on 2× A40 (TP=2) sustains ~70-80 tok/s, so a 256-token reply
    # finishes in <5s. 120s is comfortable headroom for prompt-heavy requests.
    VLLM_TIMEOUT: float = 120.0

    # ── Available model slots (for admin model switching) ──────────────────
    # Local model directory names (under /workspace/models/) shown in admin UI.
    AVAILABLE_MODELS: str = "gemma4-26b-it"

    # ── SQLite persistence ─────────────────────────────────────────────────
    INTERACTIONS_DB_PATH: str = "data/interactions.db"

    # ── Auth ──────────────────────────────────────────────────────────────
    AUTH_COOKIE_NAME: str = "gemma_session"
    AUTH_SESSION_TTL_SECONDS: int = 604800   # 7 days
    USER_SITE_PASSWORD: str = "change-me-user"
    ADMIN_SITE_PASSWORD: str = "change-me-admin"
    SESSION_SECRET_KEY: str = "change-me-secret"

    # ── API ───────────────────────────────────────────────────────────────
    API_PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    FRONTEND_ALLOWED_ORIGINS: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:9000,http://127.0.0.1:9000,"
        "http://localhost:8000,http://127.0.0.1:8000"
    )

    # ── Rate limiting ─────────────────────────────────────────────────────
    RATE_LIMIT_MAX_REQUESTS: int = 30
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # ── Generation parameters ─────────────────────────────────────────────
    MAX_NEW_TOKENS: int = 256
    TEMPERATURE: float = 0.7
    TOP_P: float = 0.9


settings = Settings()
