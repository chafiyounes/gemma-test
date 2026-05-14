#!/usr/bin/env python3
"""
Manage SQLite users (username, role, password hash) for the Gemma API.

Run from the repo root so .env / INTERACTIONS_DB_PATH resolve like the API:

    cd /workspace/gemma-test
    python3 scripts/manage_users.py list
    python3 scripts/manage_users.py add younes 'Secret!123' administrator
    python3 scripts/manage_users.py set-password younes 'NewSecret!456'
    python3 scripts/manage_users.py set-role nouhaila manager

Roles: user | manager | administrator  (alias: admin -> administrator)
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_config.settings import settings  # noqa: E402
from core.persistence import _hash_password  # noqa: E402
from core.security import AuthManager  # noqa: E402


def _db_file() -> Path:
    p = Path(settings.INTERACTIONS_DB_PATH)
    return p if p.is_absolute() else ROOT / p


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    path = _db_file()
    if not path.exists():
        print(f"Database not found: {path}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def cmd_list(_args: argparse.Namespace) -> None:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, username, role, created_at FROM users ORDER BY id"
        ).fetchall()
    if not rows:
        print("(no users)")
        return
    for r in rows:
        print(f"{r['id']:>4}  {r['username']!s:20}  {r['role']!s:16}  {r['created_at']!s}")


def cmd_add(args: argparse.Namespace) -> None:
    role = AuthManager.normalize_role(args.role)
    if role not in ("user", "manager", "administrator"):
        print("role must be user, manager, or administrator", file=sys.stderr)
        sys.exit(2)
    u = args.username.strip()
    if len(u) < 2:
        print("username too short", file=sys.stderr)
        sys.exit(2)
    h = _hash_password(args.password)
    now = _utc_now()
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                (u, h, role, now),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        print(f"User already exists: {u!r} — use set-password or set-role", file=sys.stderr)
        sys.exit(1)
    print(f"added {u!r} role={role}")


def cmd_set_password(args: argparse.Namespace) -> None:
    u = args.username.strip()
    h = _hash_password(args.password)
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ? COLLATE NOCASE",
            (h, u),
        )
        conn.commit()
        if cur.rowcount == 0:
            print(f"no such user: {u!r}", file=sys.stderr)
            sys.exit(1)
    print(f"password updated for {u!r}")


def cmd_set_role(args: argparse.Namespace) -> None:
    role = AuthManager.normalize_role(args.role)
    if role not in ("user", "manager", "administrator"):
        print("role must be user, manager, or administrator", file=sys.stderr)
        sys.exit(2)
    u = args.username.strip()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE users SET role = ? WHERE username = ? COLLATE NOCASE",
            (role, u),
        )
        conn.commit()
        if cur.rowcount == 0:
            print(f"no such user: {u!r}", file=sys.stderr)
            sys.exit(1)
    print(f"role for {u!r} set to {role}")


def main() -> None:
    p = argparse.ArgumentParser(description="Manage Gemma SQLite users")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List users (no secrets shown)").set_defaults(func=cmd_list)

    q = sub.add_parser("add", help="Create user")
    q.add_argument("username")
    q.add_argument("password")
    q.add_argument("role", help="user | manager | administrator")
    q.set_defaults(func=cmd_add)

    q = sub.add_parser("set-password", help="Set password for existing user")
    q.add_argument("username")
    q.add_argument("password")
    q.set_defaults(func=cmd_set_password)

    q = sub.add_parser("set-role", help="Set role for existing user")
    q.add_argument("username")
    q.add_argument("role")
    q.set_defaults(func=cmd_set_role)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
