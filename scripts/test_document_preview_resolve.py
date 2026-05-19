#!/usr/bin/env python3
"""Local checks for document_preview name resolution."""
from core.document_preview import _match_score, _normalize_key, resolve_document
from core.documents import get_store


def main() -> None:
    store = get_store()
    hint = "Gestion de la modification d'adresse e-mail"
    print("normalize:", _normalize_key(hint))
    resolved = resolve_document(store, hint, "procedures")
    print("resolved:", resolved)
    if resolved:
        from core.document_preview import build_preview_payload

        payload = build_preview_payload(store, hint, "procedures")
        print(
            "has_docx",
            payload["has_docx"],
            "has_md",
            payload["has_md"],
            "docx_url",
            payload.get("docx_url"),
        )


if __name__ == "__main__":
    main()
