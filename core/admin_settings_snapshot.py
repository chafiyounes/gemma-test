"""Read-only platform settings snapshot for the admin console."""

from __future__ import annotations

from typing import Any, Dict, List

from app_config.settings import Settings, settings


_SECRET_FIELD_SUBSTRINGS = (
    "PASSWORD",
    "SECRET",
    "API_KEY",
    "TOKEN",
)


def _is_secret_field(name: str) -> bool:
    upper = name.upper()
    return any(part in upper for part in _SECRET_FIELD_SUBSTRINGS)


def _format_value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _rag_mode_summary(s: Settings) -> Dict[str, Any]:
    if not s.AGENTIC_RAG_ENABLED:
        return {
            "primary_mode": "classic",
            "label": "Classic RAG uniquement",
            "agentic_available": False,
            "summary": (
                "Toutes les requêtes /chat utilisent la RAG classique (BM25 + injection DOCUMENTS DE RÉFÉRENCE). "
                "L’agentic RAG est désactivé côté serveur."
            ),
            "env_hint": "Pour activer : AGENTIC_RAG_ENABLED=true dans .env sur le pod, puis redémarrer l’API.",
        }

    rules: List[str] = [
        "Par défaut : **Classic RAG** (sauf règles ci-dessous).",
    ]
    if s.AGENTIC_RAG_DEFAULT_ON_CHAT:
        rules.append(
            "Si le client n’envoie pas `agentic_rag` : **Agentic RAG** est utilisé par défaut."
        )
    else:
        rules.append(
            "Si le client n’envoie pas `agentic_rag` : **Classic RAG** (sauf multi-scope ci-dessous)."
        )
    if s.AGENTIC_RAG_ON_MULTI_SCOPE:
        rules.append(
            "Scope **all** ou plusieurs catégories : **Agentic RAG** automatique (catalogue + outils)."
        )
    rules.append(
        "Requête explicite `agentic_rag: true` : **Agentic RAG** "
        + (
            "(tous les rôles autorisés)."
            if s.AGENTIC_RAG_ALLOW_NON_ADMIN
            else "(réservé aux sessions **administrateur**)."
        )
    )
    rules.append(
        "Requête explicite `agentic_rag: false` : **Classic RAG** forcé."
    )

    phase = (
        "Deux phases (router outils → réponse SYSTEM_PROMPT + docs)"
        if s.AGENTIC_RAG_TWO_PHASE
        else "Boucle unique (outils + réponse dans le même chat)"
    )

    return {
        "primary_mode": "agentic_when_rules_match",
        "label": "Agentic RAG activé (classic par défaut sauf règles)",
        "agentic_available": True,
        "agentic_two_phase": s.AGENTIC_RAG_TWO_PHASE,
        "agentic_phase_label": phase,
        "summary": " ; ".join(rules),
        "rules": rules,
        "env_hint": "Réglages agentic dans .env (AGENTIC_RAG_*). Redémarrage API requis après modification.",
    }


def _setting_groups(s: Settings) -> List[Dict[str, Any]]:
    def rows(prefix: str) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        for name in sorted(k for k in s.model_fields if k.startswith(prefix)):
            if _is_secret_field(name):
                continue
            out.append({"key": name, "value": _format_value(getattr(s, name))})
        return out

    def pick(names: List[str]) -> List[Dict[str, str]]:
        return [{"key": n, "value": _format_value(getattr(s, n))} for n in names]

    return [
        {
            "id": "agentic",
            "title": "Agentic RAG",
            "description": "Catalogue JSON, outils request_documents / request_logigramme, router vLLM.",
            "items": rows("AGENTIC_"),
        },
        {
            "id": "rag",
            "title": "RAG classique",
            "description": "BM25, injection DOCUMENTS DE RÉFÉRENCE, condense, cache réponses likées.",
            "items": pick(
                [
                    "RAG_DEFAULT_CATEGORY",
                    "RAG_EXTRA_CATEGORIES",
                    "RAG_INJECT_MAX_CHARS",
                    "RAG_CHAT_HISTORY_RESERVE_CHARS",
                    "LLM_MAX_CONTEXT_TOKENS",
                    "RAG_BM25_K",
                    "RAG_RETRIEVAL_CANDIDATE_K",
                    "RAG_FULL_CATEGORY_MAX_CHARS",
                    "RAG_FULL_CATEGORY_MAX_FILES",
                    "RAG_GREEDY_FULL_DOCS",
                    "RAG_CONDENSE_DOCUMENTS",
                    "RAG_REPAIR_ENABLED",
                    "LANGUAGE_REPAIR_ENABLED",
                    "CASE_BRIEF_ENABLED",
                    "CASE_BRIEF_TEMPERATURE",
                    "CASE_BRIEF_MAX_TOKENS",
                    "REASONING_REPAIR_ENABLED",
                    "RAG_ADMIN_FULL_CONTEXT_MAX_CHARS",
                    "LIKED_ANSWER_CACHE_ENABLED",
                ]
            ),
        },
        {
            "id": "generation",
            "title": "Génération (vLLM)",
            "description": "Paramètres de complétion pour le chat et les logigrammes admin.",
            "items": pick(
                [
                    "VLLM_BASE_URL",
                    "VLLM_MODEL_NAME",
                    "VLLM_TIMEOUT",
                    "MAX_NEW_TOKENS",
                    "TEMPERATURE",
                    "TOP_P",
                    "VLLM_MAX_CONTINUE_ROUNDS",
                    "VLLM_CONTINUE_MAX_TOKENS",
                    "AVAILABLE_MODELS",
                ]
            ),
        },
        {
            "id": "admin_ops",
            "title": "Administration & ops",
            "description": "Git pull depuis la console, branche, rate limit, diagnostics.",
            "items": pick(
                [
                    "ADMIN_GIT_REFRESH_ENABLED",
                    "GIT_BRANCH",
                    "API_PORT",
                    "LOG_LEVEL",
                    "API_EXPOSE_ERROR_DETAIL",
                    "RATE_LIMIT_MAX_REQUESTS",
                    "RATE_LIMIT_WINDOW_SECONDS",
                    "INTERACTIONS_DB_PATH",
                ]
            ),
        },
    ]


def build_admin_settings_snapshot(
    *,
    eval_enabled: bool,
    eval_available: bool = True,
    eval_reason: str = "",
) -> Dict[str, Any]:
    """Serializable settings for GET /api/admin/settings (no secrets)."""
    s = settings
    rag_mode = _rag_mode_summary(s)
    return {
        "rag_mode": rag_mode,
        "runtime": {
            "eval_enabled": eval_enabled,
            "eval_available": eval_available,
            "eval_reason": eval_reason or None,
            "git_refresh_allowed": bool(s.ADMIN_GIT_REFRESH_ENABLED),
            "liked_answer_cache_enabled": bool(s.LIKED_ANSWER_CACHE_ENABLED),
        },
        "groups": _setting_groups(s),
        "notes": [
            "Les valeurs ci-dessous viennent du fichier .env chargé au démarrage de l’API.",
            "Modifier .env sur le pod (/workspace/gemma-test/.env) puis bash scripts/restart_api.sh.",
            "Seul le toggle Eval est modifiable en direct depuis cette page (session API courante).",
        ],
    }
