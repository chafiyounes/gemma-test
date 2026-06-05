#!/usr/bin/env python3
"""Unit tests for grounded deduction + thread memory."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.case_brief import CaseBrief  # noqa: E402
from core.chat_policy import normalize_not_found_response  # noqa: E402
from core.deduction_policy import extract_labeled_deductions  # noqa: E402
from core.persistence import InteractionStore  # noqa: E402
from core.thread_memory import ThreadMemory, deserialize_memory  # noqa: E402


def test_extract_deductions() -> None:
    answer = (
        "1. Ouvrez la liste des colis.\n\n"
        "**Déduction :** Le délai vers Casablanca est d'environ 48h si l'expédition part du stock central.\n"
        "**Fondé sur :** Délais livraison villes, Réglementation stocks\n"
    )
    items = extract_labeled_deductions(answer)
    assert len(items) == 1
    assert "48h" in items[0]["conclusion"]
    assert "Délais" in items[0]["sources"]


def test_thread_memory_merge() -> None:
    mem = ThreadMemory(stated_facts=["Colis #123 en transit"])
    brief = CaseBrief(
        user_goal="Know delivery delay",
        stated_facts=["Stock central", "Destination Casablanca"],
        do_not_assume=["client refused"],
        retrieval_query_fr="delai livraison casablanca stock",
        action_kind="general_help",
    )
    answer = (
        "**Déduction :** Délai indicatif 48h.\n"
        "**Fondé sur :** FAQ délais\n"
    )
    updated = mem.merge_turn(brief=brief, answer=answer, user_message="delais casa?")
    assert "Stock central" in updated.stated_facts
    assert len(updated.derived_facts) == 1
    block = updated.to_prompt_block()
    assert "MÉMOIRE DU FIL" in block
    assert "48h" in block


def test_not_found_no_fake_escalation() -> None:
    out = normalize_not_found_response(
        "delivery delays to big cities?",
        "Information absent from docs. I have consulted the following documents: A, B.",
        rag_context_chars=9000,
    )
    assert "couldn't find" in out.lower() or "n'ai pas trouvé" in out.lower()
    assert "support" not in out.lower()
    assert "contact" not in out.lower()


def test_thread_memory_persistence() -> None:
    import json

    db_path = REPO_ROOT / "data" / "_test_thread_memory.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if db_path.exists():
            db_path.unlink()
        store = InteractionStore(str(db_path))
        store._initialize()
        payload = ThreadMemory(stated_facts=["test fact"]).to_metadata()
        store._save_thread_memory("sess-1", json.dumps(payload))
        raw = store._get_thread_memory("sess-1")
        mem = deserialize_memory(raw)
        assert mem.stated_facts == ["test fact"]
    finally:
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(db_path) + suffix)
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass


def main() -> None:
    test_extract_deductions()
    test_thread_memory_merge()
    test_not_found_no_fake_escalation()
    test_thread_memory_persistence()
    print("All grounded deduction tests passed.")


if __name__ == "__main__":
    main()
