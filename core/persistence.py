import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class InteractionStore:
    """SQLite-backed storage for chat interactions and user feedback."""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize)

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

    async def list_interactions(
        self,
        limit: int = 100,
        offset: int = 0,
        search: Optional[str] = None,
        feedback_value: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(
            self._list_interactions, limit, offset, search, feedback_value
        )

    def _list_interactions(
        self,
        limit: int,
        offset: int,
        search: Optional[str],
        feedback_value: Optional[str],
    ) -> List[Dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []

        if search:
            conditions.append("(i.message LIKE ? OR i.response LIKE ?)")
            params += [f"%{search}%", f"%{search}%"]
        if feedback_value:
            conditions.append("f.value = ?")
            params.append(feedback_value)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        join = "LEFT JOIN feedback f ON f.interaction_id = i.id" if feedback_value else "LEFT JOIN feedback f ON f.interaction_id = i.id"

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
        params += [limit, offset]

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
            result.append(d)
        return result

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
        return d
