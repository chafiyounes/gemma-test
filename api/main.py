import asyncio
import json
import logging
import shutil
import sqlite3
import subprocess
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import Dict, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api.schemas import (
    AdminCreateUserRequest,
    AdminUpdateUserRequest,
    AdminUserInfo,
    AdminUserListResponse,
    AuthLoginRequest,
    AuthSessionResponse,
    CategoriesResponse,
    CategoryInfo,
    ChatRequest,
    DocumentPreviewResponse,
    LogigrammeGenerateRequest,
    LogigrammeGenerateResponse,
    LogigrammeSaveRequest,
    LogigrammeStatusResponse,
    ChatResponse,
    FeedbackRequest,
    HealthResponse,
    ModelInfo,
)
from app_config.settings import settings
from core.admin_settings_snapshot import build_admin_settings_snapshot
from core.chat_policy import detect_lang_bucket, retrieval_anchor_query
from core.documents_admin import (
    apply_plan as apply_documents_plan,
    DocumentAdminError,
    delete_document,
    delete_document_category,
    get_overview as get_documents_overview,
    move_document,
    upload_document,
)
from core.document_preview import build_preview_payload, validate_file_request
from core.logigramme_service import (
    LogigrammeServiceError,
    generate_mermaid,
    get_status,
    remove_logigramme,
    save_logigramme,
    save_logigramme_draft,
)
from core.documents import DOCS_MD_DIR, get_store as get_doc_store, reload_document_store
from core.pipeline import GemmaPipeline
from core.persistence import InteractionStore
from core.security import AuthManager

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Model evaluation toggle in admin UI (no evaluator job yet — persisted for session only).
_eval_pipeline_enabled = False

APP_ROOT = Path(__file__).resolve().parent.parent
WEB_DIST_CANDIDATES = [
    APP_ROOT / "web_test" / "dist",
    APP_ROOT.parent / "web_test" / "dist",
]
ADMIN_SITE_CANDIDATES = [APP_ROOT / "admin_site"]

# Prevent browsers from keeping an old index.html that points at outdated hashed JS/CSS.
_SPA_INDEX_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
}


def _find_dir(candidates: list[Path]) -> Optional[Path]:
    for c in candidates:
        if c.is_dir():
            return c
    return None


def _resolve_rag_category(requested: Optional[str]) -> Optional[str]:
    """Pick a document folder under data/documents/ for RAG.

    If the client omits category or names an unknown folder, use RAG_DEFAULT_CATEGORY
    when present, else the first category (alphabetical).
    """
    store = get_doc_store()
    cats = store.list_categories()
    if not cats:
        return None
    names = sorted(c["name"] for c in cats)
    name_set = set(names)
    r = (requested or "").strip()
    if r in name_set:
        return r
    d = (settings.RAG_DEFAULT_CATEGORY or "").strip()
    if d in name_set:
        return d
    return names[0]


# ── Globals ───────────────────────────────────────────────────────────────────

pipeline: Optional[GemmaPipeline] = None
store: Optional[InteractionStore] = None
auth: Optional[AuthManager] = None


class MoveDocumentRequest(BaseModel):
    source_category: str
    target_category: str
    source_kind: str
    filename: str


class DeleteDocumentRequest(BaseModel):
    category: str
    source_kind: str
    filename: str


class DeleteDocumentCategoryRequest(BaseModel):
    category: str


class ApplyDocumentsPlanRequest(BaseModel):
    uploads: list[dict] = Field(default_factory=list)
    moves: list[dict] = Field(default_factory=list)
    deletes: list[dict] = Field(default_factory=list)


# ── Rate limiter ──────────────────────────────────────────────────────────────


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._windows: Dict[str, deque] = defaultdict(deque)

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        window = self._windows[key]
        cutoff = now - self.window_seconds
        while window and window[0] < cutoff:
            window.popleft()
        if len(window) >= self.max_requests:
            return False
        window.append(now)
        return True

    def remaining(self, key: str) -> int:
        now = time.time()
        window = self._windows[key]
        cutoff = now - self.window_seconds
        active = sum(1 for t in window if t >= cutoff)
        return max(0, self.max_requests - active)


rate_limiter = RateLimiter(
    max_requests=settings.RATE_LIMIT_MAX_REQUESTS,
    window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
)


def _rag_for_client(rag: dict) -> dict:
    """Hide heavy debug fields from regular /chat payloads."""
    if not isinstance(rag, dict):
        return {}
    out = dict(rag)
    out.pop("context_full", None)
    out.pop("logigramme", None)
    return out


def _chat_response_metadata(
    *,
    session: dict,
    client_ip: str,
    category_used_label: str,
    rag_meta: dict,
) -> dict:
    metadata = {
        "session_role": session["role"],
        "rate_limit_remaining": rate_limiter.remaining(client_ip),
        "category_used": category_used_label,
        "rag": _rag_for_client(rag_meta),
    }
    if isinstance(rag_meta, dict) and rag_meta.get("answer_language"):
        metadata["answer_language"] = rag_meta["answer_language"]
    logigramme = rag_meta.get("logigramme") if isinstance(rag_meta, dict) else None
    if logigramme:
        metadata["logigramme"] = logigramme
    return metadata


def _reconstruct_rag_for_admin(message: str, category: Optional[str]) -> dict:
    """Best-effort RAG reconstruction for legacy rows missing rag metadata."""
    rag: dict = {"category": category}
    if not message:
        rag["note"] = "reconstruct_empty_message"
        rag["context_chars"] = 0
        rag["documents_in_prompt"] = 0
        return rag

    try:
        store_docs = get_doc_store()
        if not category:
            category = _resolve_rag_category(None)
        if not category:
            rag["note"] = "reconstruct_no_category"
            rag["context_chars"] = 0
            rag["documents_in_prompt"] = 0
            return rag

        rag["category"] = category
        corpus = store_docs.category_corpus_chars(category)
        rq = retrieval_anchor_query(message, [])
        bucket = detect_lang_bucket(message)
        expand_hints = bucket in ("fr", "darija", "en")

        ctx = ""
        if corpus > 0 and store_docs.use_full_category_inject(category):
            ctx = store_docs.build_all_docs_context(
                category=category,
                max_chars=settings.RAG_INJECT_MAX_CHARS,
                query=rq,
                expand_for_retrieval=expand_hints,
                condense=settings.RAG_CONDENSE_DOCUMENTS,
            )
        elif corpus > 0:
            ctx = store_docs.build_context(
                rq,
                category=category,
                k=settings.RAG_BM25_K,
                max_chars=settings.RAG_INJECT_MAX_CHARS,
                expand_fr_darija_hints=expand_hints,
                condense=settings.RAG_CONDENSE_DOCUMENTS,
            )
            if not ctx:
                ctx = store_docs.build_all_docs_context(
                    category=category,
                    max_chars=settings.RAG_INJECT_MAX_CHARS,
                    query=rq,
                    expand_for_retrieval=expand_hints,
                    condense=settings.RAG_CONDENSE_DOCUMENTS,
                )

        rag["context_chars"] = len(ctx) if ctx else 0
        rag["documents_in_prompt"] = ctx.count("### Document :") if ctx else 0
        rag["context_preview"] = ctx[:900] + ("…" if len(ctx) > 900 else "") if ctx else ""
        if ctx:
            cap = max(0, int(settings.RAG_ADMIN_FULL_CONTEXT_MAX_CHARS))
            rag["context_full"] = ctx[:cap] if cap > 0 else ctx
            rag["note"] = "reconstructed_for_admin"
        else:
            rag["note"] = "reconstruct_no_context"
        return rag
    except Exception as exc:
        rag["note"] = "reconstruct_failed"
        rag["retrieval_error"] = str(exc)
        rag["context_chars"] = 0
        rag["documents_in_prompt"] = 0
        return rag


# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline, store, auth

    # Auth manager
    auth = AuthManager(
        secret_key=settings.SESSION_SECRET_KEY,
        cookie_name=settings.AUTH_COOKIE_NAME,
        session_ttl_seconds=settings.AUTH_SESSION_TTL_SECONDS,
    )
    logger.info("✓ AuthManager ready")

    # Interaction store
    store = InteractionStore(settings.INTERACTIONS_DB_PATH)
    await store.initialize()
    logger.info("✓ InteractionStore ready (%s)", settings.INTERACTIONS_DB_PATH)

    # Pipeline (non-blocking — vLLM may not be up yet at startup)
    pipeline = await asyncio.to_thread(GemmaPipeline)
    logger.info("✓ GemmaPipeline ready (model=%s)", settings.VLLM_MODEL_NAME)

    yield

    # Shutdown
    if pipeline:
        pipeline.shutdown_requested = True
        await pipeline.aclose()


# ── App factory ───────────────────────────────────────────────────────────────

allowed_origins = [o.strip() for o in settings.FRONTEND_ALLOWED_ORIGINS.split(",") if o.strip()]

app = FastAPI(
    title="Gemma Test API",
    description="Multilingual chatbot test harness — Gemma / Darija / Arabizi evaluation",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_admin_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path or ""
    if (
        path.startswith("/admin")
        or path.startswith("/admin-static")
        or path.startswith("/api/admin")
    ):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# ── Static files ──────────────────────────────────────────────────────────────

_admin_dir = _find_dir(ADMIN_SITE_CANDIDATES)
if _admin_dir:
    app.mount("/admin-static", StaticFiles(directory=str(_admin_dir / "assets")), name="admin-static")
    logger.info("Admin static files mounted from %s", _admin_dir)

_web_dist = _find_dir(WEB_DIST_CANDIDATES)
if _web_dist:
    app.mount("/assets", StaticFiles(directory=str(_web_dist / "assets")), name="web-assets")
    logger.info("Web dist mounted from %s", _web_dist)

if DOCS_MD_DIR.is_dir():
    app.mount("/api/rag-media", StaticFiles(directory=str(DOCS_MD_DIR)), name="rag-media")
    logger.info("RAG markdown / image static files mounted from %s", DOCS_MD_DIR)


# ── Exception handlers ────────────────────────────────────────────────────────


@app.exception_handler(RequestValidationError)
async def validation_exc_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": "Validation error", "errors": exc.errors()},
    )


@app.exception_handler(Exception)
async def global_exc_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    if settings.API_EXPOSE_ERROR_DETAIL:
        detail = f"Internal server error: {type(exc).__name__}: {exc}"
    else:
        detail = "Internal server error"
    return JSONResponse(status_code=500, content={"detail": detail})


# ── Dependency helpers ────────────────────────────────────────────────────────


def _get_pipeline() -> GemmaPipeline:
    if pipeline is None or pipeline.shutdown_requested:
        raise HTTPException(503, "Pipeline not ready")
    return pipeline


def _get_store() -> InteractionStore:
    if store is None:
        raise HTTPException(503, "Store not ready")
    return store


def _get_auth() -> AuthManager:
    if auth is None:
        raise HTTPException(503, "Auth not ready")
    return auth


def _read_session(request: Request, manager: AuthManager) -> Optional[dict]:
    return manager.read_session_cookie(request.cookies.get(manager.cookie_name))


async def _require_user(
    request: Request,
    manager: AuthManager = Depends(_get_auth),
) -> dict:
    session = _read_session(request, manager)
    if session is None or not manager.role_satisfies(session["role"], "user"):
        raise HTTPException(401, "Authentication required")
    return session


async def _require_administrator(
    request: Request,
    manager: AuthManager = Depends(_get_auth),
) -> dict:
    session = _read_session(request, manager)
    if session is None or not manager.role_satisfies(session["role"], "administrator"):
        raise HTTPException(403, "Administrator access required")
    return session


async def _require_docs_manager(
    request: Request,
    manager: AuthManager = Depends(_get_auth),
) -> dict:
    session = _read_session(request, manager)
    if session is None or not manager.role_satisfies(session["role"], "manager"):
        raise HTTPException(403, "Manager or administrator access required")
    return session


def _check_rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(ip):
        raise HTTPException(429, "Rate limit exceeded — please slow down")


def _set_cookie(response: Response, manager: AuthManager, value: str) -> None:
    response.set_cookie(
        key=manager.cookie_name,
        value=value,
        max_age=settings.AUTH_SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=False,
    )


def _clear_cookie(response: Response, manager: AuthManager) -> None:
    response.delete_cookie(key=manager.cookie_name, httponly=True, samesite="lax")


# ── Auth endpoints ────────────────────────────────────────────────────────────


@app.post("/auth/login", response_model=AuthSessionResponse)
async def login(
    body: AuthLoginRequest,
    response: Response,
    manager: AuthManager = Depends(_get_auth),
    db: InteractionStore = Depends(_get_store),
):
    row = db.verify_login(body.username, body.password)
    if row is None:
        raise HTTPException(401, "Identifiant ou mot de passe incorrect.")
    cookie_value, expires_at = manager.create_session_cookie(
        {"uid": row["uid"], "username": row["username"], "role": row["role"]}
    )
    _set_cookie(response, manager, cookie_value)
    return AuthSessionResponse(
        authenticated=True,
        role=row["role"],
        username=row["username"],
        user_id=row["uid"],
        expires_at=expires_at,
    )


@app.get("/auth/session", response_model=AuthSessionResponse)
async def get_session(
    request: Request,
    manager: AuthManager = Depends(_get_auth),
):
    session = _read_session(request, manager)
    if session is None:
        return AuthSessionResponse(authenticated=False)
    return AuthSessionResponse(
        authenticated=True,
        role=session["role"],
        username=session.get("username"),
        user_id=int(session["uid"]) if session.get("uid") is not None else None,
        expires_at=session["exp"],
    )


@app.get("/chat/threads")
async def list_my_threads(
    session: dict = Depends(_require_user),
    db: InteractionStore = Depends(_get_store),
):
    uid = int(session["uid"])
    return {"threads": await db.list_chat_threads(uid)}


@app.get("/chat/threads/{thread_id}/messages")
async def get_thread_messages(
    thread_id: str,
    session: dict = Depends(_require_user),
    db: InteractionStore = Depends(_get_store),
):
    uid = int(session["uid"])
    messages = await db.list_thread_messages(thread_id, uid)
    return {"messages": messages}


@app.post("/chat/threads/{thread_id}/hide", status_code=204)
async def hide_thread(
    thread_id: str,
    session: dict = Depends(_require_user),
    db: InteractionStore = Depends(_get_store),
):
    await db.hide_chat_thread(thread_id, int(session["uid"]))
    return Response(status_code=204)


@app.post("/chat/threads/hide-all", status_code=204)
async def hide_all_threads(
    session: dict = Depends(_require_user),
    db: InteractionStore = Depends(_get_store),
):
    await db.hide_all_chat_threads(int(session["uid"]))
    return Response(status_code=204)


@app.post("/auth/logout", status_code=204)
async def logout(
    response: Response,
    manager: AuthManager = Depends(_get_auth),
):
    _clear_cookie(response, manager)
    response.status_code = 204
    return response


# ── Health endpoints ──────────────────────────────────────────────────────────


@app.get("/health", response_model=HealthResponse)
async def health(p: GemmaPipeline = Depends(_get_pipeline)):
    model_ok = await p.check_health()
    return HealthResponse(
        status="ok" if model_ok else "degraded",
        model_available=model_ok,
        model_name=settings.VLLM_MODEL_NAME,
        vllm_url=settings.VLLM_BASE_URL,
    )


@app.get("/ready")
async def ready(p: GemmaPipeline = Depends(_get_pipeline)):
    model_ok = await p.check_health()
    if not model_ok:
        return JSONResponse(status_code=503, content={"ready": False, "reason": "vLLM not reachable"})
    return {"ready": True}


# ── Model info ────────────────────────────────────────────────────────────────


@app.get("/models", response_model=ModelInfo)
async def list_models():
    available = [m.strip() for m in settings.AVAILABLE_MODELS.split(",") if m.strip()]
    return ModelInfo(
        current_model=settings.VLLM_MODEL_NAME,
        available_models=available,
        vllm_url=settings.VLLM_BASE_URL,
    )


@app.get("/categories", response_model=CategoriesResponse)
async def list_categories():
    cats = get_doc_store().list_categories()
    return CategoriesResponse(
        categories=[CategoryInfo(**c) for c in cats]
    )


@app.get("/api/documents/preview", response_model=DocumentPreviewResponse)
async def document_preview(
    name: str,
    category: Optional[str] = None,
    _session: dict = Depends(_require_user),
):
    if not (name or "").strip():
        raise HTTPException(400, "Parameter 'name' is required")
    store = get_doc_store()
    try:
        payload = build_preview_payload(store, name.strip(), category)
    except LookupError:
        raise HTTPException(404, "Document introuvable")
    return DocumentPreviewResponse(**payload)


@app.get("/api/documents/file/{category}/{filename:path}")
async def document_file(
    category: str,
    filename: str,
    _session: dict = Depends(_require_user),
):
    store = get_doc_store()
    try:
        path, media_type = validate_file_request(category, filename, store)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except LookupError:
        raise HTTPException(404, "Fichier introuvable")
    return FileResponse(path, media_type=media_type, filename=filename)


# ── Chat endpoint ─────────────────────────────────────────────────────────────


@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: Request,
    body: ChatRequest,
    p: GemmaPipeline = Depends(_get_pipeline),
    db: InteractionStore = Depends(_get_store),
    session: dict = Depends(_require_user),
    auth: AuthManager = Depends(_get_auth),
    _: None = Depends(_check_rate_limit),
):
    history = [{"role": t.role, "content": t.content} for t in body.conversation_history]

    interaction_id = str(uuid.uuid4())
    client_ip = request.client.host if request.client else "unknown"
    account_id = int(session["uid"])
    user_label = str(session["username"])
    doc_store = get_doc_store()
    cats_resolved = doc_store.resolve_rag_scope(body.category)
    rag_cat_key = ",".join(sorted(cats_resolved))
    category_used_label = rag_cat_key if rag_cat_key else "none"
    category: Optional[str] = body.category

    want_agentic = False
    agentic_explicit = body.agentic_rag is True
    multi_scope = len(cats_resolved) > 1
    if body.agentic_rag is True:
        want_agentic = True
    elif body.agentic_rag is False:
        want_agentic = False
    else:
        want_agentic = bool(
            settings.AGENTIC_RAG_ENABLED and settings.AGENTIC_RAG_DEFAULT_ON_CHAT
        )
        if (
            not want_agentic
            and settings.AGENTIC_RAG_ENABLED
            and settings.AGENTIC_RAG_ON_MULTI_SCOPE
            and multi_scope
        ):
            want_agentic = True

    if want_agentic:
        if not settings.AGENTIC_RAG_ENABLED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Agentic RAG is disabled (set AGENTIC_RAG_ENABLED=true).",
            )
        if not auth.role_satisfies(session["role"], "administrator") and not settings.AGENTIC_RAG_ALLOW_NON_ADMIN:
            if agentic_explicit:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Agentic RAG is restricted to administrator sessions.",
                )
            want_agentic = False
        else:
            result = await p.process_agentic(
                message=body.message,
                history=history,
                category=category,
            )
            if not body.skip_persist:
                await db.save_interaction(
                    {
                        "id": interaction_id,
                        "user_id": user_label,
                        "account_id": account_id,
                        "session_id": body.session_id,
                        "client_ip": client_ip,
                        "model": result.model,
                        "message": body.message,
                        "response": result.response,
                        "role": session["role"],
                        "category_used": category_used_label,
                        "rag": result.rag_meta,
                    }
                )
            return ChatResponse(
                response=result.response,
                interaction_id=interaction_id,
                model=result.model,
                metadata=_chat_response_metadata(
                    session=session,
                    client_ip=client_ip,
                    category_used_label=category_used_label,
                    rag_meta=result.rag_meta,
                ),
            )

    use_liked_cache = settings.LIKED_ANSWER_CACHE_ENABLED and not body.system_prompt
    if use_liked_cache:
        cached = await db.get_cached_liked_answer(
            body.message, rag_cat_key, p.model_name
        )
        if cached is not None:
            rag_meta = {
                "category": body.category or "all",
                "categories_used": cats_resolved,
                "liked_cache_hit": True,
                "context_chars": 0,
                "documents_in_prompt": 0,
            }
            if not body.skip_persist:
                await db.save_interaction(
                    {
                        "id": interaction_id,
                        "user_id": user_label,
                        "account_id": account_id,
                        "session_id": body.session_id,
                        "client_ip": client_ip,
                        "model": p.model_name,
                        "message": body.message,
                        "response": cached,
                        "role": session["role"],
                        "category_used": category_used_label,
                        "rag": rag_meta,
                    }
                )
            return ChatResponse(
                response=cached,
                interaction_id=interaction_id,
                model=p.model_name,
                metadata={
                    "session_role": session["role"],
                    "rate_limit_remaining": rate_limiter.remaining(client_ip),
                    "category_used": category_used_label,
                    "rag": rag_meta,
                },
            )

    result = await p.process(
        message=body.message,
        history=history,
        system_prompt=body.system_prompt if auth.role_satisfies(session["role"], "administrator") else None,
        category=category,
    )

    if not body.skip_persist:
        await db.save_interaction(
            {
                "id": interaction_id,
                "user_id": user_label,
                "account_id": account_id,
                "session_id": body.session_id,
                "client_ip": client_ip,
                "model": result.model,
                "message": body.message,
                "response": result.response,
                "role": session["role"],
                "category_used": category_used_label,
                "rag": result.rag_meta,
            }
        )

    return ChatResponse(
        response=result.response,
        interaction_id=interaction_id,
        model=result.model,
        metadata=_chat_response_metadata(
            session=session,
            client_ip=client_ip,
            category_used_label=category_used_label,
            rag_meta=result.rag_meta,
        ),
    )


# ── Feedback endpoint ─────────────────────────────────────────────────────────


@app.post("/feedback", status_code=204)
async def feedback(
    body: FeedbackRequest,
    db: InteractionStore = Depends(_get_store),
    _session: dict = Depends(_require_user),
):
    await db.save_feedback(
        interaction_id=body.interaction_id,
        value=body.value,
        reason=body.reason,
        comment=body.comment,
    )
    if settings.LIKED_ANSWER_CACHE_ENABLED:
        if body.value == "like":
            await db.upsert_liked_answer_from_interaction(body.interaction_id)
        elif body.value == "dislike":
            await db.invalidate_liked_answer_for_interaction(body.interaction_id)
    return Response(status_code=204)


# ── Admin endpoints ───────────────────────────────────────────────────────────


@app.get("/admin/interactions")
async def admin_interactions(
    limit: int = 100,
    offset: int = 0,
    search: Optional[str] = None,
    feedback_value: Optional[str] = None,
    feedback_reason: Optional[str] = None,
    summary: bool = False,
    db: InteractionStore = Depends(_get_store),
    _admin: dict = Depends(_require_administrator),
):
    total = await db.count_interactions(
        search=search,
        feedback_value=feedback_value,
        feedback_reason=feedback_reason,
    )
    list_fn = db.list_interactions_summary if summary else db.list_interactions
    items = await list_fn(
        limit=limit,
        offset=offset,
        search=search,
        feedback_value=feedback_value,
        feedback_reason=feedback_reason,
    )
    return {"items": items, "count": len(items), "total": total}


@app.get("/admin/interactions/{interaction_id}")
async def admin_interaction_detail(
    interaction_id: str,
    reconstruct_rag: bool = False,
    db: InteractionStore = Depends(_get_store),
    _admin: dict = Depends(_require_administrator),
):
    item = await db.get_interaction(interaction_id)
    if item is None:
        raise HTTPException(404, "Interaction not found")
    meta = item.get("metadata") if isinstance(item, dict) else None
    if isinstance(meta, dict) and reconstruct_rag:
        rag = meta.get("rag")
        # Legacy rows can have metadata={"role": "..."} only; reconstruct on demand.
        if not isinstance(rag, dict) or not rag:
            category = meta.get("category_used")
            msg = item.get("message", "")
            meta["rag"] = _reconstruct_rag_for_admin(msg, category)
            item["metadata"] = meta
    return item


@app.get("/admin/conversations/{session_id}")
async def admin_conversation(
    session_id: str,
    db: InteractionStore = Depends(_get_store),
    _admin: dict = Depends(_require_administrator),
):
    items = await db.list_interactions_for_session(session_id)
    return {"items": items, "count": len(items)}


def _build_web_test_sync(root: Path) -> Optional[str]:
    """Run ``npm install`` + ``npm run build`` in web_test. Returns error message or None."""
    web = root / "web_test"
    if not (web / "package.json").is_file():
        return None
    npm = shutil.which("npm")
    if not npm:
        return "npm not found on PATH (install Node.js to build web_test)"
    env = {**os.environ}
    r1 = subprocess.run(
        [npm, "install"],
        cwd=str(web),
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )
    if r1.returncode != 0:
        err = (r1.stderr or r1.stdout or "").strip()
        return err or "npm install failed"
    r2 = subprocess.run(
        [npm, "run", "build"],
        cwd=str(web),
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )
    if r2.returncode != 0:
        err = (r2.stderr or r2.stdout or "").strip()
        return err or "npm run build failed"
    if not (web / "dist" / "index.html").is_file():
        return "web_test/dist/index.html missing after build"
    return None


def _git_pull_and_build_web_sync() -> dict:
    """``git fetch`` + ``reset --hard origin/<branch>`` + ``web_test`` build only (no RAG reload)."""
    root = APP_ROOT
    branch = (settings.GIT_BRANCH or "main").strip()
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    fetch = subprocess.run(
        ["git", "-C", str(root), "fetch", "origin", branch],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    if fetch.returncode != 0:
        err = (fetch.stderr or fetch.stdout or "").strip()
        return {"ok": False, "step": "fetch", "stderr": err or "git fetch failed"}
    reset = subprocess.run(
        ["git", "-C", str(root), "reset", "--hard", f"origin/{branch}"],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    if reset.returncode != 0:
        err = (reset.stderr or reset.stdout or "").strip()
        return {"ok": False, "step": "reset", "stderr": err or "git reset failed"}
    rev = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    commit = (rev.stdout or "").strip() if rev.returncode == 0 else "unknown"
    web_err = _build_web_test_sync(root)
    if web_err:
        return {"ok": False, "step": "web_build", "stderr": web_err}
    return {
        "ok": True,
        "commit": commit,
        "branch": branch,
        "web_test": "built",
        "note": (
            "Code à jour et web_test/dist reconstruit. "
            "Pour recharger uniquement les documents RAG (sans git), utilisez « Recharger index RAG ». "
            "Redémarrez l’API (ex. bash scripts/restart_api.sh) si le chat sert encore d’anciens fichiers statiques."
        ),
    }


def _rag_reload_sync() -> dict:
    """Reload DocStore / BM25 from disk (after document edits or git pull that touched data/)."""
    reload_document_store()
    cats = get_doc_store().list_categories()
    return {
        "ok": True,
        "rag_categories": cats,
        "note": f"Index RAG rechargé ({len(cats)} catégorie(s)).",
    }


@app.post("/admin/git-refresh")
@app.post("/api/admin/git-refresh")
async def admin_git_refresh(_admin: dict = Depends(_require_administrator)):
    """``git fetch`` + ``reset --hard origin/<branch>`` + build ``web_test/dist``. Does **not** reload RAG."""
    if not settings.ADMIN_GIT_REFRESH_ENABLED:
        raise HTTPException(403, detail="ADMIN_GIT_REFRESH_ENABLED=false")
    out = await asyncio.to_thread(_git_pull_and_build_web_sync)
    if not out.get("ok"):
        detail = (out.get("stderr") or out.get("step") or "git failed")[:4000]
        raise HTTPException(status_code=500, detail=detail)
    return out


@app.post("/admin/rag-reload")
@app.post("/api/admin/rag-reload")
async def admin_rag_reload(_mgr: dict = Depends(_require_docs_manager)):
    """Reload document index / BM25 only (no git, no npm)."""
    try:
        out = await asyncio.to_thread(_rag_reload_sync)
        return out
    except Exception as exc:
        logger.error("RAG reload failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)[:4000]) from exc


@app.post("/api/admin/users")
@app.post("/admin/users")
async def admin_create_user(
    body: AdminCreateUserRequest,
    db: InteractionStore = Depends(_get_store),
    _admin: dict = Depends(_require_administrator),
):
    try:
        return await asyncio.to_thread(db.create_user, body.username, body.password, body.role)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Username already exists")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/admin/users", response_model=AdminUserListResponse)
@app.get("/admin/users", response_model=AdminUserListResponse)
async def admin_list_users(
    db: InteractionStore = Depends(_get_store),
    _admin: dict = Depends(_require_administrator),
):
    rows = await asyncio.to_thread(db.list_users)
    return AdminUserListResponse(
        users=[AdminUserInfo(**r) for r in rows],
    )


@app.patch("/api/admin/users/{user_id}")
@app.patch("/admin/users/{user_id}")
async def admin_update_user(
    user_id: int,
    body: AdminUpdateUserRequest,
    db: InteractionStore = Depends(_get_store),
    _admin: dict = Depends(_require_administrator),
):
    try:
        row = await asyncio.to_thread(
            db.update_user,
            user_id,
            password=body.password,
            role=body.role,
        )
        return AdminUserInfo(**row)
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))


# ── Stub endpoints (eval / Darija toggle / cache — kept for UI compatibility) ─

@app.get("/admin/settings")
@app.get("/api/admin/settings")
async def admin_settings(_admin: dict = Depends(_require_administrator)):
    """Read-only platform settings + effective RAG mode (administrator only)."""
    return build_admin_settings_snapshot(
        eval_enabled=_eval_pipeline_enabled,
        eval_available=True,
        eval_reason="Evaluator job not wired; toggle is preparatory",
    )


@app.get("/admin/eval-status")
async def admin_eval_status(_admin: dict = Depends(_require_administrator)):
    return {
        "available": True,
        "enabled": _eval_pipeline_enabled,
        "reason": "Evaluator job not wired; toggle is preparatory",
    }


@app.post("/admin/eval-toggle")
async def admin_eval_toggle(_admin: dict = Depends(_require_administrator)):
    global _eval_pipeline_enabled
    _eval_pipeline_enabled = not _eval_pipeline_enabled
    return {"available": True, "enabled": _eval_pipeline_enabled}


@app.post("/admin/eval-run/{interaction_id}")
async def admin_eval_run(interaction_id: str, _admin: dict = Depends(_require_administrator)):
    return {"status": "skipped", "reason": "No eval system in Gemma test harness"}


@app.get("/admin/darija-status")
async def admin_darija_status(_admin: dict = Depends(_require_administrator)):
    # Darija support is handled natively by the Gemma model — no separate toggle needed
    return {
        "available": False,
        "enabled": False,
        "reason": "Darija handled by the model itself; no translation layer",
    }


@app.post("/admin/darija-toggle")
async def admin_darija_toggle(_admin: dict = Depends(_require_administrator)):
    return {"available": False, "enabled": False}


@app.post("/admin/cache-flush")
async def admin_cache_flush(_admin: dict = Depends(_require_administrator)):
    deleted = await store.flush_liked_answer_cache() if store else 0
    return {
        "deleted": deleted,
        "message": "Liked-answer cache cleared (SQLite liked_answer_cache)",
    }


@app.get("/admin/documents/overview")
@app.get("/api/admin/documents/overview")
async def admin_documents_overview(_admin: dict = Depends(_require_docs_manager)):
    return get_documents_overview(username=_admin["username"])


@app.post("/admin/documents/upload")
@app.post("/api/admin/documents/upload")
async def admin_documents_upload(
    file: UploadFile = File(...),
    category: Optional[str] = Form(None),
    _admin: dict = Depends(_require_docs_manager),
):
    if not file.filename:
        raise HTTPException(400, "Filename is required")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Uploaded file is empty")
    try:
        out = upload_document(category=category, filename=file.filename, data=data)
        reload_document_store()
        return {"ok": True, **out, "overview": get_documents_overview(username=_admin["username"])}
    except DocumentAdminError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Upload failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to upload document")


@app.post("/admin/documents/move")
@app.post("/api/admin/documents/move")
async def admin_documents_move(
    body: MoveDocumentRequest,
    _admin: dict = Depends(_require_docs_manager),
):
    try:
        out = move_document(
            source_category=body.source_category,
            target_category=body.target_category,
            source_kind=body.source_kind,
            filename=body.filename,
        )
        reload_document_store()
        return {"ok": True, **out, "overview": get_documents_overview(username=_admin["username"])}
    except DocumentAdminError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Move failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to move document")


@app.post("/admin/documents/delete")
@app.post("/api/admin/documents/delete")
async def admin_documents_delete(
    body: DeleteDocumentRequest,
    _admin: dict = Depends(_require_docs_manager),
):
    try:
        out = delete_document(
            category=body.category,
            source_kind=body.source_kind,
            filename=body.filename,
        )
        reload_document_store()
        return {"ok": True, **out, "overview": get_documents_overview(username=_admin["username"])}
    except DocumentAdminError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Delete failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete document")


@app.post("/admin/documents/delete-category")
@app.post("/api/admin/documents/delete-category")
async def admin_documents_delete_category(
    body: DeleteDocumentCategoryRequest,
    _admin: dict = Depends(_require_administrator),
):
    try:
        out = delete_document_category(body.category)
        reload_document_store()
        return {"ok": True, **out, "overview": get_documents_overview(username=_admin["username"])}
    except DocumentAdminError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Delete category failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete category")


@app.post("/admin/documents/apply-plan")
@app.post("/api/admin/documents/apply-plan")
async def admin_documents_apply_plan(
    plan_json: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    _admin: dict = Depends(_require_docs_manager),
):
    try:
        plan_raw = json.loads(plan_json)
        plan = ApplyDocumentsPlanRequest(**plan_raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid plan_json payload")

    if len(plan.uploads) != len(files):
        raise HTTPException(status_code=400, detail="Uploads/files count mismatch")

    upload_ops: list[dict] = []
    for i, upload in enumerate(plan.uploads):
        f = files[i]
        data = await f.read()
        if not data:
            raise HTTPException(status_code=400, detail=f"Empty upload: {f.filename or i}")
        filename = upload.get("filename") or f.filename
        category = upload.get("category")
        upload_ops.append({"filename": filename, "category": category, "data": data})

    try:
        overview = apply_documents_plan(
            uploads=upload_ops,
            moves=plan.moves,
            deletes=plan.deletes,
            username=_admin["username"],
        )
    except DocumentAdminError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Apply plan failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to apply plan: {exc}") from exc

    warnings: list[str] = []
    try:
        reload_document_store()
    except Exception as exc:
        logger.error("RAG reload after apply failed: %s", exc, exc_info=True)
        warnings.append(
            f"Fichiers enregistrés, mais l’index RAG n’a pas été rafraîchi ({exc}). "
            "Redémarrez l’API ou réessayez plus tard."
        )

    payload: dict = {"ok": True, "overview": overview}
    if warnings:
        payload["warnings"] = warnings
    return payload


@app.get("/api/admin/logigramme", response_model=LogigrammeStatusResponse)
async def admin_logigramme_get(
    category: str = "procedures",
    stem: str = "",
    _mgr: dict = Depends(_require_docs_manager),
):
    try:
        return LogigrammeStatusResponse(**get_status(category=category, stem=stem, username=_mgr["username"]))
    except LogigrammeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/admin/logigramme/generate", response_model=LogigrammeGenerateResponse)
async def admin_logigramme_generate(
    body: LogigrammeGenerateRequest,
    _mgr: dict = Depends(_require_docs_manager),
):
    try:
        result = generate_mermaid(
            category=body.category,
            stem=body.stem,
            messages=[m.model_dump() for m in body.messages],
            current_mermaid=body.current_mermaid,
        )
        return LogigrammeGenerateResponse(**result)
    except LogigrammeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Logigramme generate failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="Logigramme generation failed") from exc


@app.post("/api/admin/logigramme/draft")
async def admin_logigramme_save_draft(
    body: LogigrammeSaveRequest,
    _mgr: dict = Depends(_require_docs_manager),
):
    try:
        out = save_logigramme_draft(
            category=body.category,
            stem=body.stem,
            mermaid=body.mermaid,
            username=_mgr["username"],
        )
        return {**out, "overview": get_documents_overview(username=_mgr["username"])}
    except LogigrammeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Logigramme draft save failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save logigramme draft") from exc


@app.post("/api/admin/logigramme/save")
async def admin_logigramme_save(
    body: LogigrammeSaveRequest,
    _mgr: dict = Depends(_require_docs_manager),
):
    try:
        out = save_logigramme(
            category=body.category,
            stem=body.stem,
            mermaid=body.mermaid,
            username=_mgr["username"],
        )
        reload_document_store()
        return {**out, "overview": get_documents_overview(username=_mgr["username"])}
    except LogigrammeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Logigramme save failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save logigramme") from exc


@app.delete("/api/admin/logigramme")
async def admin_logigramme_delete(
    category: str = "procedures",
    stem: str = "",
    _mgr: dict = Depends(_require_docs_manager),
):
    try:
        out = remove_logigramme(category=category, stem=stem)
        reload_document_store()
        return {**out, "overview": get_documents_overview(username=_mgr["username"])}
    except LogigrammeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── Static serving ────────────────────────────────────────────────────────────


@app.get("/admin")
@app.get("/admin/")
async def serve_admin(request: Request, manager: AuthManager = Depends(_get_auth)):
    session = _read_session(request, manager)
    if session is not None and not manager.role_satisfies(session["role"], "manager"):
        raise HTTPException(403, "Accès à la console réservé aux gestionnaires et administrateurs.")
    admin_dir = _find_dir(ADMIN_SITE_CANDIDATES)
    if admin_dir:
        return FileResponse(str(admin_dir / "index.html"))
    raise HTTPException(404, "Admin site not built")


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    # Try to serve from the built web_test dist directory
    web_dist = _find_dir(WEB_DIST_CANDIDATES)
    if web_dist:
        file_path = web_dist / full_path
        if file_path.is_file():
            if file_path.name == "index.html":
                return FileResponse(str(file_path), headers=_SPA_INDEX_HEADERS)
            return FileResponse(str(file_path))
        # SPA fallback — serve index.html for all other routes
        index = web_dist / "index.html"
        if index.exists():
            return FileResponse(str(index), headers=_SPA_INDEX_HEADERS)
    # No dist yet — return helpful JSON
    return JSONResponse(
        status_code=200,
        content={
            "message": "Gemma Test API is running",
            "docs": "/docs",
            "health": "/health",
            "note": "Run 'npm run build' in web_test/ to serve the frontend here.",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=settings.API_PORT,
        reload=False,
        log_level=settings.LOG_LEVEL.lower(),
    )
