"""multilingual-e5-large embeddings for agentic map search (design-spec path).

Falls back gracefully if sentence-transformers or CUDA memory is unavailable.
E5 asymmetric retrieval: ``query:`` prefix on queries, ``passage:`` on map lines.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from app_config.settings import settings

logger = logging.getLogger(__name__)

_embedder_failed: Optional[bool] = None
_embedder = None

# (mtime, emb, ids) per category — avoids re-reading NPZ on every search_map call.
_index_cache: Dict[str, Tuple[float, np.ndarray, List[str]]] = {}


def _pick_device() -> str:
    explicit = (settings.AGENTIC_RAG_EMBEDDING_DEVICE or "").strip().lower()
    if explicit in ("cuda", "cpu", "mps"):
        return explicit
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def get_sentence_transformer():
    """Load model once per process; returns None on failure."""
    global _embedder_failed, _embedder
    if _embedder_failed:
        return None
    if _embedder is not None:
        return _embedder
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        logger.warning(
            "sentence-transformers not installed; agentic map search uses BM25. "
            "pip install sentence-transformers"
        )
        _embedder_failed = True
        return None
    model_id = settings.AGENTIC_RAG_EMBEDDING_MODEL
    device = _pick_device()
    try:
        st = SentenceTransformer(model_id, device=device)
        _embedder = st
        logger.info("Loaded embedding model %s on %s", model_id, device)
        return st
    except Exception as exc:
        logger.warning("Could not load embedding model %s: %s — BM25 fallback", model_id, exc)
        _embedder_failed = True
        return None


def embed_query(text: str) -> Optional[np.ndarray]:
    st = get_sentence_transformer()
    if st is None:
        return None
    q = (text or "").strip()
    if not q:
        return None
    prefixed = f"query: {q}"
    v = st.encode(
        prefixed,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return np.asarray(v, dtype=np.float32)


def embed_passages(texts: List[str]) -> Optional[np.ndarray]:
    st = get_sentence_transformer()
    if st is None:
        return None
    if not texts:
        return None
    prefixed = [f"passage: {(t or '').strip()}" for t in texts]
    arr = st.encode(
        prefixed,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
        batch_size=settings.AGENTIC_RAG_EMBEDDING_BATCH_SIZE,
    )
    return np.asarray(arr, dtype=np.float32)


def index_path_for_category(category: str) -> Path:
    from core.documents import REPO_ROOT

    base = Path(settings.AGENTIC_RAG_INDEX_DIR)
    if not base.is_absolute():
        base = REPO_ROOT / base
    base.mkdir(parents=True, exist_ok=True)
    safe = category.replace("/", "_").replace("..", "")
    return base / f"{safe}.npz"


def load_embedding_index(category: str) -> Optional[Tuple[np.ndarray, List[str]]]:
    """Returns (normalized embeddings nxd, ids in row order) or None."""
    path = index_path_for_category(category)
    if not path.is_file():
        return None
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    hit = _index_cache.get(category)
    if hit is not None and hit[0] == mtime:
        return hit[1], hit[2]
    try:
        data = np.load(path, allow_pickle=True)
        emb = data["emb"]
        ids = list(data["ids"])
        if emb.ndim != 2 or len(ids) != emb.shape[0]:
            return None
        emb = emb.astype(np.float32)
        _index_cache[category] = (mtime, emb, ids)
        return emb, ids
    except Exception as exc:
        logger.warning("Bad embedding index %s: %s", path, exc)
        return None


def invalidate_embedding_index_cache(category: Optional[str] = None) -> None:
    """Call after rebuilding NPZ (optional category clears one key only)."""
    if category is None:
        _index_cache.clear()
    else:
        _index_cache.pop(category, None)


def cosine_top_k(
    query_vec: np.ndarray,
    emb: np.ndarray,
    ids: List[str],
    *,
    k: int,
) -> List[Tuple[str, float]]:
    """Embeddings are L2-normalized → cosine = dot product."""
    if emb.size == 0 or not ids:
        return []
    q = query_vec.astype(np.float32).reshape(-1)
    scores = emb @ q
    order = np.argsort(-scores)
    out: List[Tuple[str, float]] = []
    for i in order[:k]:
        out.append((ids[int(i)], float(scores[int(i)])))
    return out
