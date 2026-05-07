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
    # vLLM on 2× A40 is fast; long RAG prompts + 700+ completion tokens still
    # need a generous client timeout.
    VLLM_TIMEOUT: float = 240.0

    # ── RAG (BM25 vs inject-all for small categories) ─────────────────────
    # When raw corpus size is below RAG_FULL_CATEGORY_MAX_CHARS, concatenate
    # every document in that category up to RAG_INJECT_MAX_CHARS; else BM25.
    # Optional French synonym hints on the query apply only for French/Darija
    # retrieval (English queries stay English-only). Large folders self-select BM25.
    RAG_FULL_CATEGORY_MAX_CHARS: int = 999_999
    # Hard cap per inject pass — keep headroom inside vLLM --max-model-len (often
    # 8192–12288) for instructions + chat template + completion (see start_vllm.sh).
    RAG_INJECT_MAX_CHARS: int = 24_000
    RAG_BM25_K: int = 8
    # Tighten whitespace/newlines in injected bodies so more SOP text fits the budget
    # Prefer ``data/documents_md`` (export_sop_to_md); ``documents_txt`` remains supported.
    RAG_CONDENSE_DOCUMENTS: bool = True
    # Replay answers only after explicit user « like »; dislikes remove the entry for that Q.
    LIKED_ANSWER_CACHE_ENABLED: bool = True
    # When the UI sends no category, pick this folder under data/documents/ if it
    # exists; otherwise the first category name (sorted).
    RAG_DEFAULT_CATEGORY: str = "procedures"
    # If True, omit SOP cover-sheet-style tables (titre / référence / …) from MD export.
    DOCX_MD_DROP_METADATA_TABLES: bool = False

    # ── Admin: git pull + RAG reload (no process restart for document index) ─
    ADMIN_GIT_REFRESH_ENABLED: bool = True
    GIT_BRANCH: str = "main"

    # Standard SOP numbering (sections 1–7): keep only 1..N for RAG; drop N+1 onward.
    # Set to 0 to keep the full document. Default 5 removes sections 6 and 7 when detected.
    SOP_MAX_SECTION_TO_KEEP: int = 5

    # ── Available model slots (for admin model switching) ──────────────────
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
    # Procédures longues (FR + darija, plusieurs « cas ») dépassent vite 768 sorties.
    # 2048 évite les coupures au milieu d’un mot / d’une étape (finish_reason=length).
    MAX_NEW_TOKENS: int = 2048
    TEMPERATURE: float = 0.7
    TOP_P: float = 0.9


settings = Settings()
