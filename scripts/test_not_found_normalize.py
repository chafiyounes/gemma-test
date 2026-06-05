#!/usr/bin/env python3
"""Unit tests for short not-found normalization."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.chat_policy import normalize_not_found_response  # noqa: E402

VERBOSE = (
    'Information absent from the available procedures. I have consulted the following '
    'documents: "Quels sont les différents statuts de livraison ?", '
    '"Réglementation de Gestion des Stocks".'
)


def test_inventory_collapsed() -> None:
    out = normalize_not_found_response(
        "can you give me delivery delays from stock to big cities?",
        VERBOSE,
        rag_context_chars=12000,
    )
    assert out == "I couldn't find this information."
    assert "consulted" not in out.lower()
    assert "statuts" not in out


def test_partial_answer_kept() -> None:
    partial = (
        "1. Check stock status in the menu.\n"
        "2. For city-specific lead times, information is absent from these documents."
    )
    out = normalize_not_found_response("delais livraison", partial, rag_context_chars=8000)
    assert "1. Check stock" in out


def main() -> None:
    test_inventory_collapsed()
    test_partial_answer_kept()
    print("All not-found normalize tests passed.")


if __name__ == "__main__":
    main()
