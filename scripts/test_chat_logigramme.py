#!/usr/bin/env python3
"""Tests for explicit chat logigramme intent detection and stem extraction.

Run from repo root:
  python scripts/test_chat_logigramme.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_wants_logigramme_positive() -> None:
    from core.chat_logigramme import wants_logigramme

    assert wants_logigramme("Peux-tu me faire un logigramme pour ce cas ?")
    assert wants_logigramme("Diagramme de flux du retour colis")
    assert wants_logigramme("Schéma du processus de remboursement")
    assert wants_logigramme("Show me a flowchart for this procedure")


def test_wants_logigramme_negative() -> None:
    from core.chat_logigramme import wants_logigramme

    assert not wants_logigramme("Explique étape par étape")
    assert not wants_logigramme("Comment traiter un colis endommagé ?")
    assert not wants_logigramme("")
    assert not wants_logigramme("Quelle est la procédure ?")


def test_primary_procedure_stem() -> None:
    from core.chat_logigramme import primary_procedure_stem

    ctx = (
        "### Document : retour_colis  (catégorie : help_md)\n"
        "texte\n\n"
        "### Document : procedure_remboursement  (catégorie : procedures)\n"
        "procédure\n"
    )
    assert primary_procedure_stem({"context_full": ctx}) == "procedure_remboursement"

    ctx_docx = "### Document : SOP_Stock.docx  (catégorie : procedures)\nbody"
    assert primary_procedure_stem({"context_preview": ctx_docx}) == "SOP_Stock"

    assert primary_procedure_stem({"context_full": "### Document : x  (catégorie : help_md)\n"}) is None
    assert primary_procedure_stem({}) is None


def test_augment_message_appends_instruction() -> None:
    from core.chat_logigramme import augment_message_for_logigramme

    plain = augment_message_for_logigramme("Bonjour")
    assert plain == "Bonjour"
    augmented = augment_message_for_logigramme("Donne un logigramme")
    assert "étapes numérotées" in augmented
    assert "```logigramme" in augmented


def test_extract_logigramme_fences() -> None:
    from core.chat_logigramme import extract_logigramme_fences

    raw = (
        "Voici les étapes.\n\n"
        "```logigramme\nflowchart TD\nA-->B\n```\n\n"
        "Source: Proc-test"
    )
    text, codes = extract_logigramme_fences(raw)
    assert "flowchart TD" not in text
    assert "Voici les étapes" in text
    assert codes == ["flowchart TD\nA-->B"]


def main() -> None:
    test_wants_logigramme_positive()
    test_wants_logigramme_negative()
    test_primary_procedure_stem()
    test_augment_message_appends_instruction()
    test_extract_logigramme_fences()
    print("test_chat_logigramme: OK")


if __name__ == "__main__":
    main()
