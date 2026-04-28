import asyncio
import logging
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.schemas import (
    AuthLoginRequest,
    AuthSessionResponse,
    ChatRequest,
    ChatResponse,
    FeedbackRequest,
    HealthResponse,
    ModelInfo,
)
from app_config.settings import settings
from core.pipeline import GemmaPipeline
from core.persistence import InteractionStore
from core.security import AuthManager

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

APP_ROOT = Path(__file__).resolve().parent.parent
WEB_DIST_CANDIDATES = [
    APP_ROOT / "web_test" / "dist",
    APP_ROOT.parent / "web_test" / "dist",
]
ADMIN_SITE_CANDIDATES = [APP_ROOT / "admin_site"]


def _find_dir(candidates: list[Path]) -> Optional[Path]:
    for c in candidates:
        if c.is_dir():
            return c
    return None


# ── Globals ───────────────────────────────────────────────────────────────────

pipeline: Optional[GemmaPipeline] = None
store: Optional[InteractionStore] = None
auth: Optional[AuthManager] = None


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


# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline, store, auth

    # Auth manager
    auth = AuthManager(
        secret_key=settings.SESSION_SECRET_KEY,
        user_password=settings.USER_SITE_PASSWORD,
        admin_password=settings.ADMIN_SITE_PASSWORD,
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


# ── Static files ──────────────────────────────────────────────────────────────

_admin_dir = _find_dir(ADMIN_SITE_CANDIDATES)
if _admin_dir:
    app.mount("/admin-static", StaticFiles(directory=str(_admin_dir / "assets")), name="admin-static")
    logger.info("Admin static files mounted from %s", _admin_dir)

_web_dist = _find_dir(WEB_DIST_CANDIDATES)
if _web_dist:
    app.mount("/assets", StaticFiles(directory=str(_web_dist / "assets")), name="web-assets")
    logger.info("Web dist mounted from %s", _web_dist)


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
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


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


async def _require_admin(
    request: Request,
    manager: AuthManager = Depends(_get_auth),
) -> dict:
    session = _read_session(request, manager)
    if session is None or not manager.role_satisfies(session["role"], "admin"):
        raise HTTPException(403, "Admin access required")
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
):
    role = manager.authenticate(body.password)
    if role is None:
        raise HTTPException(401, "Invalid password")
    cookie_value, expires_at = manager.create_session_cookie(role)
    _set_cookie(response, manager, cookie_value)
    return AuthSessionResponse(authenticated=True, role=role, expires_at=expires_at)


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
        expires_at=session["exp"],
    )


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


# ── Chat endpoint ─────────────────────────────────────────────────────────────


@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: Request,
    body: ChatRequest,
    p: GemmaPipeline = Depends(_get_pipeline),
    db: InteractionStore = Depends(_get_store),
    session: dict = Depends(_require_user),
    _: None = Depends(_check_rate_limit),
):
    history = [{"role": t.role, "content": t.content} for t in body.conversation_history]

    result = await p.process(
        message=body.message,
        history=history,
        system_prompt=body.system_prompt if session["role"] == "admin" else None,
    )

    interaction_id = str(uuid.uuid4())
    client_ip = request.client.host if request.client else "unknown"

    if not body.skip_persist:
        asyncio.create_task(
            db.save_interaction(
                {
                    "id": interaction_id,
                    "user_id": body.user_id,
                    "session_id": body.session_id,
                    "client_ip": client_ip,
                    "model": result.model,
                    "message": body.message,
                    "response": result.response,
                    "role": session["role"],
                }
            )
        )

    return ChatResponse(
        response=result.response,
        interaction_id=interaction_id,
        model=result.model,
        metadata={
            "session_role": session["role"],
            "rate_limit_remaining": rate_limiter.remaining(client_ip),
        },
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
    return Response(status_code=204)


# ── Admin endpoints ───────────────────────────────────────────────────────────


@app.get("/admin/interactions")
async def admin_interactions(
    limit: int = 100,
    offset: int = 0,
    search: Optional[str] = None,
    feedback_value: Optional[str] = None,
    db: InteractionStore = Depends(_get_store),
    _admin: dict = Depends(_require_admin),
):
    items = await db.list_interactions(
        limit=limit,
        offset=offset,
        search=search,
        feedback_value=feedback_value,
    )
    return {"items": items, "count": len(items)}


@app.get("/admin/interactions/{interaction_id}")
async def admin_interaction_detail(
    interaction_id: str,
    db: InteractionStore = Depends(_get_store),
    _admin: dict = Depends(_require_admin),
):
    item = await db.get_interaction(interaction_id)
    if item is None:
        raise HTTPException(404, "Interaction not found")
    return item


@app.get("/admin/conversations/{session_id}")
async def admin_conversation(
    session_id: str,
    db: InteractionStore = Depends(_get_store),
    _admin: dict = Depends(_require_admin),
):
    items = await db.list_interactions(limit=200, search=None)
    filtered = [i for i in items if i.get("session_id") == session_id]
    return {"items": filtered, "count": len(filtered)}


# ── Stub endpoints (eval / Darija toggle / cache — kept for UI compatibility) ─

@app.get("/admin/eval-status")
async def admin_eval_status(_admin: dict = Depends(_require_admin)):
    # Evaluation not implemented in this test harness
    return {"available": False, "enabled": False, "reason": "No eval system in Gemma test harness"}


@app.post("/admin/eval-toggle")
async def admin_eval_toggle(_admin: dict = Depends(_require_admin)):
    return {"available": False, "enabled": False}


@app.post("/admin/eval-run/{interaction_id}")
async def admin_eval_run(interaction_id: str, _admin: dict = Depends(_require_admin)):
    return {"status": "skipped", "reason": "No eval system in Gemma test harness"}


@app.get("/admin/darija-status")
async def admin_darija_status(_admin: dict = Depends(_require_admin)):
    # Darija support is handled natively by the Gemma model — no separate toggle needed
    return {
        "available": False,
        "enabled": False,
        "reason": "Darija handled by the model itself; no translation layer",
    }


@app.post("/admin/darija-toggle")
async def admin_darija_toggle(_admin: dict = Depends(_require_admin)):
    return {"available": False, "enabled": False}


@app.post("/admin/cache-flush")
async def admin_cache_flush(_admin: dict = Depends(_require_admin)):
    # No Redis cache in this project
    return {"deleted": 0, "message": "No cache in use (no Redis)"}


# ── Static serving ────────────────────────────────────────────────────────────


@app.get("/admin")
@app.get("/admin/")
async def serve_admin():
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
            return FileResponse(str(file_path))
        # SPA fallback — serve index.html for all other routes
        index = web_dist / "index.html"
        if index.exists():
            return FileResponse(str(index))
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
