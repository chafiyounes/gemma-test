#!/usr/bin/env python3
"""Unit tests for case brief JSON parsing and reasoning compliance (no vLLM)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.case_brief import (  # noqa: E402
    CaseBrief,
    parse_case_brief_payload,
    retrieval_query_with_brief,
)
from core.chat_policy import retrieval_anchor_query  # noqa: E402
from core.reasoning_compliance import (  # noqa: E402
    compose_system_prompt_with_case_brief,
    violates_case_brief,
)


def test_parse_valid_brief() -> None:
    obj = {
        "user_goal": "Verify why parcel shows Annulé when client says livreur never came",
        "stated_facts": ["Status Annulé", "Client says livreur did not come"],
        "do_not_assume": ["Client refused the parcel", "Livreur could not deliver"],
        "retrieval_query_fr": "statut Annulé colis vérifier liste des colis livreur",
        "action_kind": "verify_status",
    }
    brief = parse_case_brief_payload(obj)
    assert brief is not None
    assert brief.action_kind == "verify_status"
    assert len(brief.stated_facts) == 2
    assert "refused" in brief.do_not_assume[0].lower() or "refus" in brief.do_not_assume[0].lower()


def test_parse_invalid_missing_goal() -> None:
    assert parse_case_brief_payload({"stated_facts": []}) is None


def test_retrieval_query_prefers_brief() -> None:
    brief = CaseBrief(
        user_goal="x",
        retrieval_query_fr="statut colis vérifier annulation",
    )
    rq = retrieval_query_with_brief("chno ndir?", [], brief)
    assert "vérifier" in rq or "verifier" in rq.lower()


def test_retrieval_query_fallback_anchor() -> None:
    msg = "where is history?"
    hist = [
        {"role": "user", "content": "colis injoignable livreur"},
        {"role": "assistant", "content": "ok"},
    ]
    rq = retrieval_query_with_brief(msg, hist, None)
    assert "injoignable" in rq.lower() or "colis" in rq.lower()


def test_compose_injects_cas_utilisateur() -> None:
    brief = CaseBrief(
        user_goal="Check parcel status",
        stated_facts=["Annulé shown"],
        do_not_assume=["Client refused"],
    )
    out = compose_system_prompt_with_case_brief("## Rôle\nBot\n\n## Priorité\nX", brief)
    assert "CAS UTILISATEUR" in out
    assert "Check parcel status" in out
    assert out.index("CAS UTILISATEUR") < out.index("## Priorité")


def test_violates_case_brief_detects_assumption() -> None:
    brief = CaseBrief(
        user_goal="Verify status",
        do_not_assume=["Client refused the order before livreur came"],
    )
    bad = (
        "Le colis est marqué Annulé car le client a refusé la commande "
        "avant que le livreur ne se déplace."
    )
    assert violates_case_brief(bad, brief)


def test_violates_case_brief_conditional_ok() -> None:
    brief = CaseBrief(
        user_goal="Verify status",
        do_not_assume=["Client refused the order"],
    )
    ok = "Si le client a vraiment refusé, voir la procédure refus. Sinon vérifier le statut."
    assert not violates_case_brief(ok, brief)


def main() -> None:
    test_parse_valid_brief()
    test_parse_invalid_missing_goal()
    test_retrieval_query_prefers_brief()
    test_retrieval_query_fallback_anchor()
    test_compose_injects_cas_utilisateur()
    test_violates_case_brief_detects_assumption()
    test_violates_case_brief_conditional_ok()
    print("All case brief unit tests passed.")


if __name__ == "__main__":
    main()
