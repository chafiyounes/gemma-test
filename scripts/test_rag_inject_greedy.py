#!/usr/bin/env python3
"""Regression tests for depth-first RAG injection (no thin slice per file).

Run from repo root:
  python scripts/test_rag_inject_greedy.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _partial_markers(s: str) -> int:
    return s.count("…(tronqué)") + s.count("début du document omis")


def _make_docs(names: list[str], cat: str, body: str) -> list:
    from core.documents import Doc, _tokenize

    out = []
    for name in names:
        toks = _tokenize(body)
        out.append(Doc(name=name, category=cat, text=body, tokens=toks, tf=Counter(toks)))
    return out


def _category_index(cat: str, docs: list):
    from core.documents import CategoryIndex

    df: Counter[str] = Counter()
    total_len = 0
    for d in docs:
        for t in d.tf:
            df[t] += 1
        total_len += len(d.tokens)
    return CategoryIndex(
        name=cat,
        docs=docs,
        df=df,
        avgdl=total_len / len(docs) if docs else 1.0,
    )


def test_all_full_when_fits() -> None:
    from core.documents import _greedy_inject_document_blocks

    entries = [(f"### Document : f{i}  (catégorie : x)\n", "line\n" * 40) for i in range(12)]
    blocks = _greedy_inject_document_blocks(
        entries,
        query="test query",
        max_chars=500_000,
        expand_fr_darija_hints=False,
    )
    assert len(blocks) == 12, len(blocks)
    blob = "".join(blocks)
    assert _partial_markers(blob) == 0, blob[:500]


def test_at_most_one_partial_many_large_docs() -> None:
    from core.documents import _greedy_inject_document_blocks

    # Several large bodies: all eight cannot be full under 50k; greedy must not return 8 slivers.
    big = "SECTION\n" * 2000 + "ENDMARK\n"
    assert len(big) >= 12_000
    entries = [(f"### Document : p{i}  (catégorie : c)\n", big) for i in range(8)]
    blocks = _greedy_inject_document_blocks(
        entries,
        query="ENDMARK section procedure",
        max_chars=50_000,
        expand_fr_darija_hints=False,
    )
    blob = "\n".join(blocks)
    assert _partial_markers(blob) <= 1, f"partial markers={_partial_markers(blob)}"
    assert len(blocks) <= 5, f"expected a handful of blocks (full + one partial), got {len(blocks)}"


def test_partial_then_more_full_in_remaining_budget() -> None:
    from core.documents import _greedy_inject_document_blocks

    entries = [
        ("### Document : A  (catégorie : c)\n", ("alpha\n" * 2000) + "STEP99 unique anchor\n" + ("tail\n" * 50)),
        ("### Document : B  (catégorie : c)\n", "short B\n" * 8),
        ("### Document : C  (catégorie : c)\n", "short C\n" * 8),
    ]
    blocks = _greedy_inject_document_blocks(
        entries,
        query="STEP99 anchor vendeur",
        max_chars=25_000,
        expand_fr_darija_hints=False,
    )
    assert len(blocks) >= 2, blocks
    blob = "".join(blocks)
    assert "short B" in blob or "short C" in blob, blob[:1200]


def test_build_context_real_store_few_partials() -> None:
    import types

    from core.documents import DocStore

    big = "proc\n" * 4000 + "ENDX\n"
    docs = _make_docs([str(i) for i in range(6)], "k", big)
    store = DocStore.__new__(DocStore)
    store.indexes = {"k": _category_index("k", docs)}

    def _fake_retrieve(
        self,
        query,
        category=None,
        *,
        categories=None,
        k=5,
        expand_fr_darija_hints=False,
    ):
        return docs[:k]

    store.retrieve = types.MethodType(_fake_retrieve, store)
    ctx = DocStore.build_context(
        store,
        "ENDX proc",
        category="k",
        k=5,
        max_chars=14_000,
        expand_fr_darija_hints=False,
        condense=False,
    )
    assert _partial_markers(ctx) <= 1, ctx[:2000]
    assert ctx.count("### Document :") <= 4


def test_build_all_docs_overflow_few_partials() -> None:
    from core.documents import DocStore

    bodies = [("block\n" * 900) + f"marker{i}\n" for i in range(7)]
    docs = [_make_docs([str(i)], "cat", bodies[i])[0] for i in range(7)]
    store = DocStore.__new__(DocStore)
    store.indexes = {"cat": _category_index("cat", docs)}

    ctx = DocStore.build_all_docs_context(
        store,
        category="cat",
        max_chars=28_000,
        query="marker3",
        expand_for_retrieval=False,
        condense=False,
    )
    assert _partial_markers(ctx) <= 1, ctx[:2500]
    assert ctx.count("### Document :") <= 6


def test_multi_category_retrieve_prefers_global_relevance() -> None:
    from core.documents import DocStore

    help_body = "article général aide support " * 50
    proc_body = "procédure livraison colis téléphone modification vendeur " * 30
    help_docs = _make_docs([f"help{i}" for i in range(8)], "help_md", help_body)
    proc_docs = _make_docs(["sop_livraison"], "procedures", proc_body)
    store = DocStore.__new__(DocStore)
    store.indexes = {
        "help_md": _category_index("help_md", help_docs),
        "procedures": _category_index("procedures", proc_docs),
    }
    top = store.retrieve(
        "modification téléphone colis livraison vendeur",
        categories=["help_md", "procedures"],
        k=3,
        expand_fr_darija_hints=False,
    )
    assert top, "expected retrieval hits"
    assert top[0].category == "procedures", [f"{d.category}/{d.name}" for d in top]


def test_validate_mermaid_skips_init_directive() -> None:
    from core.mermaid_validate import normalize_mermaid, validate_mermaid

    raw = (
        "%%{init: {'flowchart': {'htmlLabels': true}}}%%\n"
        "flowchart TD\n"
        "  A[Début] --> B[Fin]\n"
    )
    assert validate_mermaid(raw)
    cleaned = normalize_mermaid(raw)
    assert cleaned.startswith("flowchart TD")


def test_format_retrieved_agentic_greedy() -> None:
    from core.agentic_rag import format_retrieved_documents_for_prompt

    id_to_text = {f"id{i}": "LINE\n" * 5000 for i in range(5)}
    text = format_retrieved_documents_for_prompt(
        category="c",
        id_to_text=id_to_text,
        ordered_ids=["id0", "id1", "id2", "id3", "id4"],
        max_chars=18_000,
        condense=False,
        anchor_query="LINE procedure",
        expand_fr_darija_hints=False,
    )
    assert _partial_markers(text) <= 1
    assert text.count("### Document :") <= 3


def test_mermaid_completeness_heuristic() -> None:
    from core.logigramme_llm import count_mermaid_nodes, estimate_procedure_steps, mermaid_looks_incomplete

    proc = "\n".join([f"{i}. Étape importante numéro {i}" for i in range(1, 12)])
    assert estimate_procedure_steps(proc) >= 10
    sparse = "flowchart TD\n  A[Début] --> B[Fin]\n"
    rich = "flowchart TD\n" + "\n".join(f"  n{i}[Étape {i}] --> n{i+1}[Suite {i}]" for i in range(12))
    assert mermaid_looks_incomplete(proc, sparse)
    assert not mermaid_looks_incomplete(proc, rich)
    assert count_mermaid_nodes(rich) >= 12


def test_logigramme_draft_storage() -> None:
    import tempfile

    import core.logigrammes_store as store

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig = store.LOGIGRAMMES_DIR
        store.LOGIGRAMMES_DIR = root
        try:
            m = "flowchart TD\n  A[Début] --> B[Fin]\n"
            store.save_draft("procedures", "test_sop", m)
            assert store.draft_exists("procedures", "test_sop")
            assert store.read_draft("procedures", "test_sop") == m.strip()
            assert not store.exists("procedures", "test_sop")
            store.save("procedures", "test_sop", m)
            assert store.exists("procedures", "test_sop")
            assert not store.draft_exists("procedures", "test_sop")
        finally:
            store.LOGIGRAMMES_DIR = orig


def main() -> None:
    test_all_full_when_fits()
    test_at_most_one_partial_many_large_docs()
    test_partial_then_more_full_in_remaining_budget()
    test_build_context_real_store_few_partials()
    test_build_all_docs_overflow_few_partials()
    test_multi_category_retrieve_prefers_global_relevance()
    test_validate_mermaid_skips_init_directive()
    test_mermaid_completeness_heuristic()
    test_logigramme_draft_storage()
    test_format_retrieved_agentic_greedy()
    print("rag_inject_greedy: OK (11 tests)")


if __name__ == "__main__":
    main()
