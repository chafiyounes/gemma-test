#!/usr/bin/env python3
"""Exercise admin document staging rules + apply_plan using local files.

The browser drag/drop path cannot be driven from this script; this mirrors the
same category mapping as admin_site/assets/admin.js (assignFolderFilesToCategories)
and either:

  --dry-plan   Print planned categories only (no writes).
  --local      Call core.documents_admin.apply_plan in-process (needs repo CWD).
  --http URL   POST /api/admin/documents/apply-plan with admin cookie (API must run).

Search order for inputs:
  1) REPO/data/documents/temp  (if it exists and has .txt/.docx)
  2) REPO/scripts/fixtures/documents_temp

Examples:
  python scripts/test_admin_documents_from_temp.py --dry-plan
  python scripts/test_admin_documents_from_temp.py --dry-plan --corpus fixtures
  python scripts/test_admin_documents_from_temp.py --local --corpus fixtures
  python scripts/test_admin_documents_from_temp.py --dry-plan --corpus temp
  python scripts/test_admin_documents_from_temp.py --http http://127.0.0.1:8000 --corpus fixtures
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO_ROOT / "scripts" / "fixtures" / "documents_temp"
USER_TEMP = REPO_ROOT / "data" / "documents" / "temp"


def iter_doc_files(root: Path) -> Iterable[Path]:
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in (".txt", ".docx"):
            yield p


def discover_root(corpus: str) -> Path:
    if corpus == "fixtures":
        if FIXTURE_ROOT.is_dir() and any(iter_doc_files(FIXTURE_ROOT)):
            return FIXTURE_ROOT
        raise SystemExit(f"No files under {FIXTURE_ROOT}")
    if corpus == "temp":
        if USER_TEMP.is_dir() and any(iter_doc_files(USER_TEMP)):
            return USER_TEMP
        raise SystemExit(f"No .txt/.docx under {USER_TEMP}")
    # auto: prefer user temp, else fixtures
    if USER_TEMP.is_dir():
        for p in USER_TEMP.rglob("*"):
            if p.is_file() and p.suffix.lower() in (".txt", ".docx"):
                return USER_TEMP
    if FIXTURE_ROOT.is_dir():
        return FIXTURE_ROOT
    raise SystemExit(
        f"No temp corpus found. Create {USER_TEMP} with .txt/.docx or use fixtures at {FIXTURE_ROOT}"
    )


def assign_folder_paths(
    paths: list[tuple[Path, str]], fallback_category: str
) -> tuple[list[tuple[Path, str]], list[str]]:
    """Mirror admin JS assignFolderFilesToCategories for posix relative paths."""
    assignments: list[tuple[Path, str]] = []
    errors: list[str] = []
    by_root: dict[str, dict] = {}

    for path, rel in paths:
        lower = path.name.lower()
        if not (lower.endswith(".txt") or lower.endswith(".docx")):
            continue
        rel = rel.replace("\\", "/")
        if not rel:
            assignments.append((path, fallback_category))
            continue
        parts = [x for x in rel.split("/") if x]
        if len(parts) < 2:
            assignments.append((path, fallback_category))
            continue
        root = parts[0]
        sub_path_depth = len(parts) - 2
        grp = by_root.setdefault(root, {"files": []})
        if sub_path_depth == 0:
            grp["has_direct"] = True
        grp["files"].append({"path": path, "parts": parts, "sub": sub_path_depth})

    for root, grp in by_root.items():
        files = grp["files"]
        has_subfolders = any(f["sub"] >= 1 for f in files)
        for item in files:
            if item["sub"] >= 2:
                errors.append(
                    f'Arborescence trop profonde dans "{"/".join(item["parts"])}" (max: root/category/file).'
                )
                continue
            if has_subfolders:
                if item["sub"] == 0:
                    errors.append(
                        f'Fichier a la racine de "{root}" non autorise quand des sous-dossiers existent: "{"/".join(item["parts"])}".'
                    )
                    continue
                assignments.append((item["path"], item["parts"][1]))
            else:
                assignments.append((item["path"], root))

    return assignments, errors


def build_plan(root: Path, fallback: str) -> tuple[dict, list[str]]:
    rel_items: list[tuple[Path, str]] = []
    for p in iter_doc_files(root):
        rel = p.relative_to(root).as_posix()
        rel_items.append((p, rel))

    assignments, errors = assign_folder_paths(rel_items, fallback)
    uploads = []
    for path, category in assignments:
        uploads.append(
            {"category": category, "filename": path.name, "data": path.read_bytes()}
        )
    plan = {"uploads": [{"category": u["category"], "filename": u["filename"]} for u in uploads], "moves": [], "deletes": []}
    return plan, errors, uploads


def run_local(uploads: list[dict]) -> None:
    os.chdir(REPO_ROOT)
    sys.path.insert(0, str(REPO_ROOT))
    from core.documents import reload_document_store
    from core.documents_admin import DocumentAdminError, apply_plan

    try:
        overview = apply_plan(uploads=uploads, moves=[], deletes=[])
        reload_document_store()
        print("apply_plan: OK")
        cats = overview.get("categories") or []
        print(json.dumps({"categories": len(cats), "corpus": overview.get("corpus")}, indent=2))
        print(f"categories now: {len(cats)}")
        for c in cats:
            if c["name"] in {u["category"] for u in uploads}:
                print(f"  - {c['name']}: {c['file_count']} files, {c['total_chars']} chars")
    except DocumentAdminError as e:
        print("apply_plan failed:", e)
        sys.exit(1)


def run_http(base: str, plan: dict, uploads: list[dict]) -> None:
    import urllib.error
    import urllib.request

    pw = os.environ.get("ADMIN_SITE_PASSWORD", "").strip()
    if not pw:
        print("Set ADMIN_SITE_PASSWORD for --http", file=sys.stderr)
        sys.exit(2)
    admin_user = os.environ.get("AUTH_BOOTSTRAP_ADMIN_USERNAME", "admin").strip() or "admin"

    jar = []

    def opener(req):
        if jar:
            req.add_header("Cookie", jar[0])
        return urllib.request.urlopen(req, timeout=120)

    login = urllib.request.Request(
        f"{base.rstrip('/')}/auth/login",
        data=json.dumps({"username": admin_user, "password": pw}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with opener(login) as r:
        c = r.headers.get("Set-Cookie") or ""
        for part in c.split(","):
            if "gemma_session=" in part:
                jar.append(part.split(";")[0].strip())
                break
        if not jar:
            print("Login failed: no session cookie", file=sys.stderr)
            sys.exit(2)

    boundary = "----gemmaTempBoundary"
    lines: list[bytes] = []
    plan_part = json.dumps(plan)
    lines.append(f"--{boundary}\r\n".encode())
    lines.append(b'Content-Disposition: form-data; name="plan_json"\r\n\r\n')
    lines.append(plan_part.encode() + b"\r\n")

    for u in uploads:
        raw = u["data"]
        fname = u["filename"]
        lines.append(f"--{boundary}\r\n".encode())
        lines.append(
            f'Content-Disposition: form-data; name="files"; filename="{fname}"\r\n'.encode()
        )
        lines.append(b"Content-Type: application/octet-stream\r\n\r\n")
        lines.append(raw + b"\r\n")
    lines.append(f"--{boundary}--\r\n".encode())
    body = b"".join(lines)

    req = urllib.request.Request(
        f"{base.rstrip('/')}/api/admin/documents/apply-plan",
        data=body,
        method="POST",
    )
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    if jar:
        req.add_header("Cookie", jar[0])

    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            out = json.loads(r.read().decode())
            print("HTTP apply-plan: OK")
            ov = out.get("overview") or {}
            print(json.dumps({"categories": len(ov.get("categories") or []), "corpus": ov.get("corpus")}, indent=2))
    except urllib.error.HTTPError as e:
        print("HTTP error:", e.code, e.read().decode()[:2000])
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--corpus",
        choices=("auto", "temp", "fixtures"),
        default="auto",
        help="auto: data/documents/temp if it has files, else scripts/fixtures/documents_temp",
    )
    ap.add_argument("--fallback", default="procedures", help="Category when path has no folder prefix")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-plan", action="store_true")
    g.add_argument("--local", action="store_true")
    g.add_argument("--http", metavar="BASE_URL")
    args = ap.parse_args()

    root = discover_root(args.corpus)
    print(f"Using corpus root: {root}")
    plan, errors, uploads = build_plan(root, args.fallback)
    if errors:
        print("Mapping warnings/errors:")
        for e in errors:
            print(" ", e)
    print("Planned uploads:")
    for u in plan["uploads"]:
        print(f"  {u['filename']} -> category {u['category']}")

    if args.dry_plan:
        return

    if args.local:
        run_local(uploads)
    else:
        run_http(args.http, plan, uploads)


if __name__ == "__main__":
    main()
