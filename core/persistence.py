import asyncio
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class InteractionStore:
    """SQLite-backed storage for chat interactions and user feedback."""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)

    @staticmethod
    def liked_answer_cache_key(message: str, category: Optional[str], model: str) -> str:
        """Stable key: normalized message + RAG category + model name."""
        norm = " ".join((message or "").split())
        cat = (category or "").strip()
        mod = (model or "").strip()
        payload = f"{norm}\n{cat}\n{mod}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize)

    @staticmethod
    def _finalize_interaction(d: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Nest feedback fields for admin UI; drop raw SQL column aliases."""
        if d is None:
            return None
        d = dict(d)
        fv = d.pop("feedback_value", None)
        fr = d.pop("feedback_reason", None)
        fc = d.pop("feedback_comment", None)
        if fv:
            d["feedback"] = {"value": fv, "reason": fr, "comment": fc}
        else:
            d["feedback"] = None
        return d

    def _initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS interactions (
                    id          TEXT PRIMARY KEY,
                    created_at  TEXT NOT NULL,
                    user_id     TEXT NOT NULL,
                    session_id  TEXT,
                    client_ip   TEXT,
                    model       TEXT,
                    message     TEXT NOT NULL,
                    response    TEXT NOT NULL,
                    metadata_json TEXT
                );

                CREATE TABLE IF NOT EXISTS feedback (
                    interaction_id TEXT PRIMARY KEY,
                    value          TEXT NOT NULL CHECK(value IN ('like', 'dislike')),
                    reason         TEXT,
                    comment        TEXT,
                    created_at     TEXT NOT NULL,
                    updated_at     TEXT NOT NULL,
                    FOREIGN KEY(interaction_id) REFERENCES interactions(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_interactions_created_at
                    ON interactions(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_interactions_session_id
                    ON interactions(session_id);
                CREATE INDEX IF NOT EXISTS idx_feedback_value
                    ON feedback(value);

                CREATE TABLE IF NOT EXISTS liked_answer_cache (
                    cache_key      TEXT PRIMARY KEY,
                    message        TEXT NOT NULL,
                    category       TEXT NOT NULL,
                    model          TEXT NOT NULL,
                    response       TEXT NOT NULL,
                    interaction_id TEXT,
                    created_at     TEXT NOT NULL,
                    updated_at     TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _to_json(obj: Any) -> Optional[str]:
        if obj is None:
            return None
        try:
            return json.dumps(obj, ensure_ascii=False)
        except Exception:
            return None

    async def save_interaction(self, interaction: Dict[str, Any]) -> Dict[str, Any]:
        return await asyncio.to_thread(self._save_interaction, interaction)

    def _save_interaction(self, interaction: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(interaction)
        payload.setdefault("created_at", self._utc_now())
        metadata = {
            k: v for k, v in payload.items()
            if k not in {"id", "created_at", "user_id", "session_id",
                         "client_ip", "model", "message", "response"}
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO interactions
                    (id, created_at, user_id, session_id, client_ip, model, message, response, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["id"],
                    payload["created_at"],
                    payload.get("user_id", "anonymous"),
                    payload.get("session_id"),
                    payload.get("client_ip"),
                    payload.get("model"),
                    payload["message"],
                    payload["response"],
                    self._to_json(metadata or None),
                ),
            )
        return payload

    async def save_feedback(self, interaction_id: str, value: str, reason: Optional[str], comment: Optional[str]) -> None:
        await asyncio.to_thread(self._save_feedback, interaction_id, value, reason, comment)

    def _save_feedback(self, interaction_id: str, value: str, reason: Optional[str], comment: Optional[str]) -> None:
        now = self._utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO feedback (interaction_id, value, reason, comment, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(interaction_id) DO UPDATE SET
                    value=excluded.value, reason=excluded.reason,
                    comment=excluded.comment, updated_at=excluded.updated_at
                """,
                (interaction_id, value, reason, comment, now, now),
            )

    def _filter_sql(
        self,
        search: Optional[str],
        feedback_value: Optional[str],
        feedback_reason: Optional[str],
    ) -> tuple[str, list[Any]]:
        conditions: list[str] = []
        params: list[Any] = []

        if search:
            conditions.append(
                "(i.message LIKE ? OR i.response LIKE ? OR IFNULL(f.comment, '') LIKE ?)"
            )
            like = f"%{search}%"
            params += [like, like, like]
        if feedback_value:
            conditions.append("f.value = ?")
            params.append(feedback_value)
        if feedback_reason:
            conditions.append("f.reason = ?")
            params.append(feedback_reason)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        return where, params

    async def count_interactions(
        self,
        search: Optional[str] = None,
        feedback_value: Optional[str] = None,
        feedback_reason: Optional[str] = None,
    ) -> int:
        return await asyncio.to_thread(
            self._count_interactions, search, feedback_value, feedback_reason
        )

    def _count_interactions(
        self,
        search: Optional[str],
        feedback_value: Optional[str],
        feedback_reason: Optional[str],
    ) -> int:
        where, params = self._filter_sql(search, feedback_value, feedback_reason)
        join = "LEFT JOIN feedback f ON f.interaction_id = i.id"
        query = f"""
            SELECT COUNT(DISTINCT i.id)
            FROM interactions i
            {join}
            {where}
        """
        with self._connect() as conn:
            row = conn.execute(query, params).fetchone()
        return int(row[0]) if row else 0

    async def list_interactions(
        self,
        limit: int = 100,
        offset: int = 0,
        search: Optional[str] = None,
        feedback_value: Optional[str] = None,
        feedback_reason: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(
            self._list_interactions,
            limit,
            offset,
            search,
            feedback_value,
            feedback_reason,
        )

    def _list_interactions(
        self,
        limit: int,
        offset: int,
        search: Optional[str],
        feedback_value: Optional[str],
        feedback_reason: Optional[str],
    ) -> List[Dict[str, Any]]:
        where, params = self._filter_sql(search, feedback_value, feedback_reason)
        join = "LEFT JOIN feedback f ON f.interaction_id = i.id"

        query = f"""
            SELECT
                i.id, i.created_at, i.user_id, i.session_id, i.model,
                i.message, i.response, i.metadata_json,
                f.value AS feedback_value, f.reason AS feedback_reason, f.comment AS feedback_comment
            FROM interactions i
            {join}
            {where}
            ORDER BY i.created_at DESC
            LIMIT ? OFFSET ?
        """
        params = list(params) + [limit, offset]

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        result = []
        for row in rows:
            d = dict(row)
            raw_meta = d.pop("metadata_json", None)
            try:
                d["metadata"] = json.loads(raw_meta) if raw_meta else {}
            except Exception:
                d["metadata"] = {}
            fin = self._finalize_interaction(d)
            if fin:
                result.append(fin)
        return result

    async def list_interactions_for_session(
        self, session_id: str, limit: int = 500
    ) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(
            self._list_interactions_for_session, session_id, limit
        )

    def _list_interactions_for_session(
        self, session_id: str, limit: int
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT
                i.id, i.created_at, i.user_id, i.session_id, i.model,
                i.message, i.response, i.metadata_json,
                f.value AS feedback_value, f.reason AS feedback_reason, f.comment AS feedback_comment
            FROM interactions i
            LEFT JOIN feedback f ON f.interaction_id = i.id
            WHERE i.session_id = ?
            ORDER BY i.created_at ASC
            LIMIT ?
        """
        with self._connect() as conn:
            rows = conn.execute(query, (session_id, limit)).fetchall()
        out = []
        for row in rows:
            d = dict(row)
            raw_meta = d.pop("metadata_json", None)
            try:
                d["metadata"] = json.loads(raw_meta) if raw_meta else {}
            except Exception:
                d["metadata"] = {}
            fin = self._finalize_interaction(d)
            if fin:
                out.append(fin)
        return out

    async def get_interaction(self, interaction_id: str) -> Optional[Dict[str, Any]]:
        return await asyncio.to_thread(self._get_interaction, interaction_id)

    def _get_interaction(self, interaction_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT i.*, f.value AS feedback_value, f.reason AS feedback_reason, f.comment AS feedback_comment
                FROM interactions i
                LEFT JOIN feedback f ON f.interaction_id = i.id
                WHERE i.id = ?
                """,
                (interaction_id,),
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        raw_meta = d.pop("metadata_json", None)
        try:
            d["metadata"] = json.loads(raw_meta) if raw_meta else {}
        except Exception:
            d["metadata"] = {}
        return self._finalize_interaction(d)

    async def get_cached_liked_answer(
        self, message: str, category: Optional[str], model: str
    ) -> Optional[str]:
        return await asyncio.to_thread(
            self._get_cached_liked_answer, message, category, model
        )

    def _get_cached_liked_answer(
        self, message: str, category: Optional[str], model: str
    ) -> Optional[str]:
        key = self.liked_answer_cache_key(message, category, model)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT response FROM liked_answer_cache WHERE cache_key = ?",
                (key,),
            ).fetchone()
        return str(row[0]) if row else None

    async def upsert_liked_answer_from_interaction(self, interaction_id: str) -> None:
        await asyncio.to_thread(self._upsert_liked_answer_from_interaction, interaction_id)

    def _upsert_liked_answer_from_interaction(self, interaction_id: str) -> None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT i.message, i.response, i.model, i.metadata_json
                FROM interactions i
                WHERE i.id = ?
                """,
                (interaction_id,),
            ).fetchone()
        if row is None:
            return
        message, response, model, raw_meta = row[0], row[1], row[2], row[3]
        try:
            meta = json.loads(raw_meta) if raw_meta else {}
        except Exception:
            meta = {}
        category = meta.get("category_used") or ""
        key = self.liked_answer_cache_key(message, category, model)
        now = self._utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO liked_answer_cache
                    (cache_key, message, category, model, response, interaction_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    response=excluded.response,
                    interaction_id=excluded.interaction_id,
                    updated_at=excluded.updated_at
                """,
                (key, message, category, model, response, interaction_id, now, now),
            )

    async def invalidate_liked_answer_for_interaction(self, interaction_id: str) -> None:
        await asyncio.to_thread(self._invalidate_liked_answer_for_interaction, interaction_id)

    def _invalidate_liked_answer_for_interaction(self, interaction_id: str) -> None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT i.message, i.model, i.metadata_json
                FROM interactions i
                WHERE i.id = ?
                """,
                (interaction_id,),
            ).fetchone()
        if row is None:
            return
        message, model, raw_meta = row[0], row[1], row[2]
        try:
            meta = json.loads(raw_meta) if raw_meta else {}
        except Exception:
            meta = {}
        category = meta.get("category_used") or ""
        key = self.liked_answer_cache_key(message, category, model)
        with self._connect() as conn:
            conn.execute("DELETE FROM liked_answer_cache WHERE cache_key = ?", (key,))

    async def flush_liked_answer_cache(self) -> int:
        return await asyncio.to_thread(self._flush_liked_answer_cache)

    def _flush_liked_answer_cache(self) -> int:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM liked_answer_cache")
            return int(cur.rowcount or 0)
