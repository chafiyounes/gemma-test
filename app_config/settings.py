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
    # "Inject all" only when the corpus is small *and* file count is low; otherwise
    # BM25 top-k runs first (avoids slicing every document into useless snippets).
    # Optional French synonym hints on the query apply only for French/Darija
    # retrieval (English queries stay English-only).
    RAG_FULL_CATEGORY_MAX_CHARS: int = 72_000
    RAG_FULL_CATEGORY_MAX_FILES: int = 10
    # Hard ceiling per inject pass (effective budget is usually **lower** — see
    # ``_compute_rag_inject_limit_chars`` in core/llm.py using LLM_MAX_CONTEXT_TOKENS).
    RAG_INJECT_MAX_CHARS: int = 22_000
    # Must match vLLM ``--max-model-len`` on the pod (4096 / 8192 / 16384 / …).
    LLM_MAX_CONTEXT_TOKENS: int = 16_384
    # Rough chars-per-token for budgeting mixed FR/Darija/EN (conservative).
    RAG_BUDGET_CHARS_PER_TOKEN: float = 3.0
    # Extra tokens reserved for chat template, special tokens, JSON overhead — not doc text.
    RAG_BUDGET_OVERHEAD_TOKENS: int = 600
    # Reserve part of the prompt budget for conversation history so long chats keep coherence.
    RAG_CHAT_HISTORY_RESERVE_CHARS: int = 12_000
    RAG_BM25_K: int = 12
    # Rank up to this many documents **across all merged categories** (flat pool;
    # category stays metadata on each chunk). Greedy / max_chars trims what actually
    # goes into the prompt — this is retrieval breadth, not injection size.
    RAG_RETRIEVAL_CANDIDATE_K: int = 100
    # When the corpus exceeds the inject budget: prefer **complete** top-ranked files
    # and at most **one** partial (query-aligned), instead of thin slices of many files.
    RAG_GREEDY_FULL_DOCS: bool = True
    # Skip emitting a partial unless at least this many chars fit (avoids useless scraps).
    RAG_MIN_CHARS_FOR_PARTIAL: int = 1200
    # Tighten whitespace/newlines in injected bodies so more SOP text fits the budget
    # Prefer ``data/documents_md`` (export_sop_to_md); ``documents_txt`` remains supported.
    RAG_CONDENSE_DOCUMENTS: bool = True
    # Persist full injected document block for admin inspection (DB metadata).
    # Client-facing /chat metadata still strips this field.
    RAG_ADMIN_FULL_CONTEXT_MAX_CHARS: int = 120_000
    # If True (default), run a second vLLM turn when the model claims “not in docs” despite a large inject.
    # Disable for debugging or if repair adds latency without benefit.
    RAG_REPAIR_ENABLED: bool = True
    # Replay answers only after explicit user « like »; dislikes remove the entry for that Q.
    LIKED_ANSWER_CACHE_ENABLED: bool = True
    # Default document corpus folder under data/documents_md|txt|…/<name>/ and the
    # default /chat category when the client omits category. Admin bulk uploads use
    # this when the category field is left empty (single corpus + catalog lookup).
    RAG_DEFAULT_CATEGORY: str = "procedures"
    # Comma-separated extra corpus names (must exist under data/documents/<name>/)
    # merged into RAG retrieval together with the primary category from the chat UI.
    # Help-center Markdown under data/documents_md/help_md/ (comma-separated aliases OK).
    RAG_EXTRA_CATEGORIES: str = "help_md,help_articles"
    # If True, omit SOP cover-sheet-style tables (titre / référence / …) from MD export.
    DOCX_MD_DROP_METADATA_TABLES: bool = False

    # ── Agentic RAG (optional; see project/ARCHITECTURE.md § agentic) ───────
    # When enabled, POST /chat with "agentic_rag": true uses map + tools instead
    # of injecting DOCUMENTS DE RÉFÉRENCE. Requires vLLM tool calling + map JSON.
    AGENTIC_RAG_ENABLED: bool = False
    # If True, phase 1 routes with tools only (English router prompt); phase 2 answers
    # with normal SYSTEM_PROMPT + DOCUMENTS DE RÉFÉRENCE (full retrieved bodies).
    # If False, legacy single-loop (routing + answer in one tool-chat).
    AGENTIC_RAG_TWO_PHASE: bool = True
    # Retrieval router: unique document IDs to load before the answer phase (cap across rounds).
    AGENTIC_RAG_ROUTER_MAX_TOTAL_IDS: int = 10
    # Max ids per `request_documents` tool call (Gemma sees 1–N per round in the router prompt).
    AGENTIC_RAG_ROUTER_MAX_IDS_PER_ROUND: int = 5
    # Router tool-call rounds (retry when the first batch is plausible but wrong).
    AGENTIC_RAG_ROUTER_MAX_ROUNDS: int = 3
    # Prompt guidance only — aim for about this many documents when the catalog is large.
    AGENTIC_RAG_ROUTER_TARGET_DOCS: int = 5
    # If True, treat agentic as on when the client omits agentic_rag (None).
    # Non-admin users still need AGENTIC_RAG_ALLOW_NON_ADMIN or they get classic RAG.
    AGENTIC_RAG_DEFAULT_ON_CHAT: bool = False
    # If False, only admin sessions may set agentic_rag on /chat.
    AGENTIC_RAG_ALLOW_NON_ADMIN: bool = False
    # When True, multi-category scopes (e.g. "all") auto-use agentic catalog routing.
    AGENTIC_RAG_ON_MULTI_SCOPE: bool = True
    # BM25 pre-filter: max catalog rows sent to the router prompt.
    AGENTIC_RAG_CATALOG_NARROW_MAX: int = 40
    AGENTIC_RAG_MAP_DIR: str = "data/agentic_map"
    # Lower temperature stabilizes tool selection vs default chat TEMPERATURE.
    AGENTIC_RAG_TEMPERATURE: float = 0.35
    # Design-spec retrieval: multilingual-e5-large + cosine on title+tags (see core/agentic_embeddings.py).
    # If False or model missing, search_map falls back to BM25.
    AGENTIC_RAG_USE_EMBEDDINGS: bool = True
    AGENTIC_RAG_EMBEDDING_MODEL: str = "intfloat/multilingual-e5-large"
    # cuda | cpu | mps | empty = auto (cuda if available)
    AGENTIC_RAG_EMBEDDING_DEVICE: str = ""
    AGENTIC_RAG_EMBEDDING_BATCH_SIZE: int = 32
    # NPZ index built by scripts/build_agentic_embedding_index.py (one file per category).
    AGENTIC_RAG_INDEX_DIR: str = "data/agentic_index"
    # Top hit cosine similarity below this → low_confidence (design doc ~0.5).
    AGENTIC_RAG_MAP_CONFIDENCE_THRESHOLD: float = 0.5
    # Optional smaller/faster model for map extraction (OpenAI name on vLLM). Empty = VLLM_MODEL_NAME.
    AGENTIC_MAP_EXTRACTION_MODEL: Optional[str] = None

    # ── Admin: git pull + RAG reload (no process restart for document index) ─
    ADMIN_GIT_REFRESH_ENABLED: bool = True
    GIT_BRANCH: str = "main"

    # Standard SOP numbering (sections 1–7): keep only 1..N for RAG; drop N+1 onward.
    # Default is 0 (disabled) to avoid dropping potentially useful procedure detail.
    SOP_MAX_SECTION_TO_KEEP: int = 0

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
    AUTH_BOOTSTRAP_ADMIN_USERNAME: str = "admin"
    AUTH_BOOTSTRAP_USER_USERNAME: str = "user"
    # One-time seed for named staff (SQLite row created only if username is missing).
    SEED_STAFF_YOUNES_PASSWORD: str = ""
    SEED_STAFF_NOUHAILA_PASSWORD: str = ""
    # If True, non-empty SEED_STAFF_* passwords also UPDATE existing rows on startup
    # (use once on a pod to fix a wrong password, then set back to false).
    SEED_STAFF_SYNC_PASSWORDS: bool = False

    # ── API ───────────────────────────────────────────────────────────────
    API_PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    # If True, JSON 500 responses include exception type + message (diagnostics on the pod only).
    API_EXPOSE_ERROR_DETAIL: bool = False
    FRONTEND_ALLOWED_ORIGINS: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:9000,http://127.0.0.1:9000,"
        "http://localhost:8000,http://127.0.0.1:8000"
    )

    # ── Rate limiting ─────────────────────────────────────────────────────
    RATE_LIMIT_MAX_REQUESTS: int = 30
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # ── Generation parameters ─────────────────────────────────────────────
    # 2048 aligns with .env.example; reduces mid-answer truncation (vLLM finish_reason=length).
    MAX_NEW_TOKENS: int = 2048
    TEMPERATURE: float = 0.7
    TOP_P: float = 0.9
    # If the model hits max length mid-answer, send continuation turn(s) (same thread).
    VLLM_MAX_CONTINUE_ROUNDS: int = 5
    VLLM_CONTINUE_MAX_TOKENS: int = 2048


settings = Settings()
