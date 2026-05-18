import asyncio
import base64
import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app_config.settings import settings
from core.security import AuthManager


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return "pbkdf2$310000$" + base64.b64encode(salt).decode("ascii") + "$" + base64.b64encode(dk).decode("ascii")


def _verify_password(password: str, stored: str) -> bool:
    if not stored or "$" not in stored:
        return False
    parts = stored.split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2":
        return False
    try:
        iters = int(parts[1])
        salt = base64.b64decode(parts[2].encode("ascii"))
        want = base64.b64decode(parts[3].encode("ascii"))
    except Exception:
        return False
    got = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters)
    return secrets.compare_digest(got, want)


class InteractionStore:
    """SQLite-backed storage for chat interactions and user feedback."""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)

    @staticmethod
    def liked_answer_cache_key(message: str, category: Optional[str], model: str) -> str:
        """Stable key: normalized message + RAG category (may be merged list) + model name."""
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
                CREATE TABLE IF NOT EXISTS users (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    username       TEXT NOT NULL UNIQUE,
                    password_hash  TEXT NOT NULL,
                    role           TEXT NOT NULL,
                    created_at     TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chat_threads (
                    id          TEXT PRIMARY KEY,
                    user_id     INTEGER NOT NULL,
                    title       TEXT NOT NULL DEFAULT 'New chat',
                    visible     INTEGER NOT NULL DEFAULT 1,
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_chat_threads_user_visible
                    ON chat_threads(user_id, visible, updated_at DESC);

                CREATE TABLE IF NOT EXISTS interactions (
                    id          TEXT PRIMARY KEY,
                    created_at  TEXT NOT NULL,
                    user_id     TEXT NOT NULL,
                    session_id  TEXT,
                    client_ip   TEXT,
                    model       TEXT,
                    message     TEXT NOT NULL,
                    response    TEXT NOT NULL,
                    metadata_json TEXT,
                    account_id  INTEGER
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
            self._migrate_legacy_columns(conn)
            self._migrate_users_role_schema(conn)
            self._bootstrap_users(conn)
            self._seed_named_staff(conn)

    def _migrate_legacy_columns(self, conn: sqlite3.Connection) -> None:
        info = {row[1] for row in conn.execute("PRAGMA table_info(interactions)")}
        if "account_id" not in info:
            try:
                conn.execute("ALTER TABLE interactions ADD COLUMN account_id INTEGER")
            except sqlite3.OperationalError:
                pass
        try:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_interactions_account_session "
                "ON interactions(account_id, session_id, created_at)"
            )
        except sqlite3.OperationalError:
            pass
        conn.commit()

    def _migrate_users_role_schema(self, conn: sqlite3.Connection) -> None:
        """Allow user / manager / administrator: rebuild table if legacy CHECK constraints exist."""
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        if not row or not row[0]:
            return
        ddl = (row[0] or "").lower()
        if "check" not in ddl:
            conn.execute(
                "UPDATE users SET role = 'administrator' WHERE lower(role) = 'admin'"
            )
            conn.commit()
            return
        conn.executescript(
            """
            PRAGMA foreign_keys = OFF;
            CREATE TABLE users__new (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                username       TEXT NOT NULL UNIQUE,
                password_hash  TEXT NOT NULL,
                role           TEXT NOT NULL,
                created_at     TEXT NOT NULL
            );
            INSERT INTO users__new (id, username, password_hash, role, created_at)
            SELECT id, username, password_hash,
                   CASE role
                     WHEN 'admin' THEN 'administrator'
                     ELSE role
                   END,
                   created_at
            FROM users;
            DROP TABLE users;
            ALTER TABLE users__new RENAME TO users;
            PRAGMA foreign_keys = ON;
            """
        )
        conn.commit()

    def _seed_named_staff(self, conn: sqlite3.Connection) -> None:
        """Upsert younes / nouhaila (or other env-driven seeds) when passwords are set."""
        specs = [
            ("younes", settings.SEED_STAFF_YOUNES_PASSWORD, "administrator"),
            ("nouhaila", settings.SEED_STAFF_NOUHAILA_PASSWORD, "manager"),
        ]
        changed = False
        now = self._utc_now()
        for uname, raw_pw, role in specs:
            pw = (raw_pw or "").strip()
            if not pw:
                continue
            if role not in ("user", "manager", "administrator"):
                continue
            uname = (uname or "").strip()
            if not uname:
                continue
            h = _hash_password(pw)
            row = conn.execute(
                "SELECT id FROM users WHERE username = ? COLLATE NOCASE",
                (uname,),
            ).fetchone()
            if row:
                if settings.SEED_STAFF_SYNC_PASSWORDS:
                    conn.execute(
                        "UPDATE users SET password_hash = ?, role = ? WHERE id = ?",
                        (h, role, int(row[0])),
                    )
                    changed = True
                continue
            conn.execute(
                "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                (uname, h, role, now),
            )
            changed = True
        if changed:
            conn.commit()

    def _bootstrap_users(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
        if row and int(row[0]) > 0:
            return
        now = self._utc_now()
        admin_name = (settings.AUTH_BOOTSTRAP_ADMIN_USERNAME or "admin").strip()
        user_name = (settings.AUTH_BOOTSTRAP_USER_USERNAME or "user").strip()
        conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (admin_name, _hash_password(settings.ADMIN_SITE_PASSWORD), "administrator", now),
        )
        conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (user_name, _hash_password(settings.USER_SITE_PASSWORD), "user", now),
        )
        conn.commit()

    def verify_login(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        u = (username or "").strip()
        if not u or not password:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, username, password_hash, role FROM users WHERE username = ? COLLATE NOCASE",
                (u,),
            ).fetchone()
        if row is None:
            return None
        uid, name, phash, role = int(row[0]), str(row[1]), str(row[2]), str(row[3])
        if not _verify_password(password, phash):
            return None
        norm = AuthManager.normalize_role(role)
        return {"uid": uid, "username": name, "role": norm}

    def create_user(self, username: str, password: str, role: str) -> Dict[str, Any]:
        r = AuthManager.normalize_role(role)
        if r not in ("user", "manager", "administrator"):
            raise ValueError("role must be user, manager, or administrator")
        u = (username or "").strip()
        if len(u) < 2:
            raise ValueError("username too short")
        now = self._utc_now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                (u, _hash_password(password), r, now),
            )
            uid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        return {"uid": uid, "username": u, "role": r}

    def list_users(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, username, role, created_at
                FROM users
                ORDER BY username COLLATE NOCASE
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def update_user(
        self,
        uid: int,
        *,
        password: Optional[str] = None,
        role: Optional[str] = None,
    ) -> Dict[str, Any]:
        if password is None and role is None:
            raise ValueError("nothing to update")
        new_role: Optional[str] = None
        if role is not None:
            new_role = AuthManager.normalize_role(role)
            if new_role not in ("user", "manager", "administrator"):
                raise ValueError("role must be user, manager, or administrator")
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM users WHERE id = ?", (uid,)).fetchone()
            if row is None:
                raise ValueError("user not found")
            if password is not None:
                conn.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (_hash_password(password), uid),
                )
            if new_role is not None:
                conn.execute(
                    "UPDATE users SET role = ? WHERE id = ?",
                    (new_role, uid),
                )
            conn.commit()
            row2 = conn.execute(
                "SELECT id, username, role, created_at FROM users WHERE id = ?",
                (uid,),
            ).fetchone()
        if row2 is None:
            raise ValueError("user missing after update")
        return dict(row2)

    async def list_chat_threads(self, account_id: int) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._list_chat_threads, account_id)

    def _list_chat_threads(self, account_id: int) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM chat_threads
                WHERE user_id = ? AND visible = 1
                ORDER BY updated_at DESC
                LIMIT 200
                """,
                (account_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    async def hide_chat_thread(self, thread_id: str, account_id: int) -> None:
        await asyncio.to_thread(self._hide_chat_thread, thread_id, account_id)

    def _hide_chat_thread(self, thread_id: str, account_id: int) -> None:
        tid = (thread_id or "").strip()
        if not tid:
            return
        with self._connect() as conn:
            conn.execute(
                "UPDATE chat_threads SET visible = 0 WHERE id = ? AND user_id = ?",
                (tid, account_id),
            )

    async def hide_all_chat_threads(self, account_id: int) -> None:
        await asyncio.to_thread(self._hide_all_chat_threads, account_id)

    def _hide_all_chat_threads(self, account_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE chat_threads SET visible = 0 WHERE user_id = ? AND visible = 1",
                (account_id,),
            )

    async def list_thread_messages(self, thread_id: str, account_id: int) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._list_thread_messages, thread_id, account_id)

    def _list_thread_messages(self, thread_id: str, account_id: int) -> List[Dict[str, Any]]:
        tid = (thread_id or "").strip()
        if not tid:
            return []
        with self._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM chat_threads WHERE id = ? AND user_id = ? AND visible = 1",
                (tid, account_id),
            ).fetchone()
            if not exists:
                return []
            rows = conn.execute(
                """
                SELECT
                    i.id, i.created_at, i.message, i.response, i.metadata_json,
                    f.value AS feedback_value, f.reason AS feedback_reason, f.comment AS feedback_comment
                FROM interactions i
                LEFT JOIN feedback f ON f.interaction_id = i.id
                WHERE i.session_id = ? AND IFNULL(i.account_id, -1) = ?
                ORDER BY i.created_at ASC
                """,
                (tid, account_id),
            ).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            d = dict(row)
            meta_raw = d.pop("metadata_json", None)
            try:
                meta = json.loads(meta_raw) if meta_raw else {}
            except Exception:
                meta = {}
            fv = d.pop("feedback_value", None)
            fr = d.pop("feedback_reason", None)
            fc = d.pop("feedback_comment", None)
            feedback = None
            if fv:
                feedback = {"value": fv, "reason": fr, "comment": fc}
            assistant_payload = {
                    "role": "assistant",
                    "content": d["response"],
                    "interactionId": d["id"],
                    "feedback": feedback,
                    "metadata": meta,
                    "created_at": d["created_at"],
                }
            out.append(
                {
                    "role": "user",
                    "content": d["message"],
                    "interaction_id": None,
                }
            )
            out.append(
                assistant_payload
            )
        return out

    def _upsert_chat_thread(self, conn: sqlite3.Connection, thread_id: str, account_id: int, title: str) -> None:
        tid = (thread_id or "").strip()
        if not tid:
            return
        now = self._utc_now()
        title_clean = (title or "New chat").strip() or "New chat"
        if len(title_clean) > 200:
            title_clean = title_clean[:197] + "..."
        row = conn.execute(
            "SELECT title FROM chat_threads WHERE id = ? AND user_id = ?",
            (tid, account_id),
        ).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO chat_threads (id, user_id, title, visible, created_at, updated_at)
                VALUES (?, ?, ?, 1, ?, ?)
                """,
                (tid, account_id, title_clean, now, now),
            )
            return
        prev_title = (row[0] or "").strip()
        new_title = title_clean
        if prev_title and prev_title not in ("New chat", "Nouvelle conversation") and title_clean in ("New chat", "Nouvelle conversation"):
            new_title = prev_title
        conn.execute(
            """
            UPDATE chat_threads
            SET title = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (new_title, now, tid, account_id),
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
            if k not in {
                "id", "created_at", "user_id", "session_id",
                "client_ip", "model", "message", "response", "account_id",
            }
        }
        acct = payload.get("account_id")
        sid_raw = payload.get("session_id")
        with self._connect() as conn:
            if acct is not None and sid_raw:
                title_hint = (payload.get("message") or "").strip().replace("\n", " ")
                if len(title_hint) > 120:
                    title_hint = title_hint[:117] + "..."
                self._upsert_chat_thread(conn, str(sid_raw), int(acct), title_hint or "New chat")
            conn.execute(
                """
                INSERT INTO interactions
                    (id, created_at, user_id, session_id, client_ip, model, message, response, metadata_json, account_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    int(acct) if acct is not None else None,
                ),
            )
            conn.commit()
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
