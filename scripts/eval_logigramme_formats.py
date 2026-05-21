#!/usr/bin/env python3
"""Evaluate logigramme output formats via direct vLLM calls (pod / SSH only)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx

from app_config.settings import settings
from core.documents import get_store
from core.logigramme_llm import SUPPORTED_FORMATS, generate_logigramme, load_procedure_text


def _pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate logigramme formats on procedures.")
    parser.add_argument(
        "--stems",
        default="Gestion des colis endommag_,Demande de remboursement - colis endommag_,Pr_paration des colis",
        help="Comma-separated document stems",
    )
    parser.add_argument("--category", default="procedures")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--formats", default=",".join(SUPPORTED_FORMATS))
    parser.add_argument("--output-dir", default=str(ROOT / "outputs" / "logigramme_eval"))
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    stems = [s.strip() for s in args.stems.split(",") if s.strip()]
    formats = [f.strip() for f in args.formats.split(",") if f.strip()]
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    store = get_store()
    base_url = settings.VLLM_BASE_URL.rstrip("/")
    print(f"vLLM: {base_url}")
    print(f"Stems: {stems}")
    print(f"Formats: {formats}")

    trials: list[dict] = []
    summary: dict[str, dict] = {f: {"valid": 0, "total": 0, "retries": 0} for f in formats}

    with httpx.Client(base_url=base_url, timeout=120.0) as client:
        for stem in stems:
            try:
                doc_text = load_procedure_text(store, args.category, stem)
            except ValueError as exc:
                print(f"SKIP {stem}: {exc}")
                continue
            for fmt in formats:
                for trial in range(1, args.trials + 1):
                    print(f"  {stem} | {fmt} | trial {trial}/{args.trials}...")
                    try:
                        outcome = generate_logigramme(
                            document_text=doc_text,
                            fmt=fmt,
                            client=client,
                            model=args.model,
                        )
                    except Exception as exc:
                        outcome = None
                        err = str(exc)
                        trials.append(
                            {
                                "stem": stem,
                                "format": fmt,
                                "trial": trial,
                                "syntax_valid": False,
                                "error": err,
                            }
                        )
                        summary[fmt]["total"] += 1
                        continue

                    artifact = out_dir / f"{stem}_{fmt}_t{trial}.{ _ext(fmt) }"
                    if outcome and outcome.cleaned:
                        artifact.write_text(outcome.cleaned + "\n", encoding="utf-8")

                    row = {
                        "stem": stem,
                        "format": fmt,
                        "trial": trial,
                        "syntax_valid": outcome.syntax_valid if outcome else False,
                        "structure_count": outcome.structure_count if outcome else 0,
                        "retried": outcome.retried if outcome else False,
                        "latency_ms": outcome.latency_ms if outcome else 0,
                        "artifact": str(artifact.name) if outcome and outcome.cleaned else "",
                        "error": outcome.error if outcome else "",
                        "preview": (outcome.cleaned[:400] if outcome else ""),
                    }
                    trials.append(row)
                    summary[fmt]["total"] += 1
                    if row["syntax_valid"]:
                        summary[fmt]["valid"] += 1
                    if row.get("retried"):
                        summary[fmt]["retries"] += 1

    report = {
        "timestamp": ts,
        "stems": stems,
        "formats": formats,
        "trials_per_format": args.trials,
        "summary": {
            f: {
                **summary[f],
                "valid_pct": _pct(summary[f]["valid"], summary[f]["total"]),
            }
            for f in formats
        },
        "trials": trials,
    }

    json_path = out_dir / f"report_{ts}.json"
    md_path = out_dir / f"report_{ts}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# Logigramme format evaluation ({ts})",
        "",
        "## Summary (automated syntax)",
        "",
        "| Format | Valid | Total | Valid % | Retries |",
        "|--------|-------|-------|---------|---------|",
    ]
    for f in formats:
        s = report["summary"][f]
        lines.append(
            f"| {f} | {s['valid']} | {s['total']} | {s['valid_pct']}% | {s['retries']} |"
        )
    lines.extend(
        [
            "",
            "## Manual fidelity review (1–5)",
            "",
            "Open artifacts in this folder. Score each: steps match procedure, no invented branches.",
            "",
            "## Gate for web integration",
            "",
            "- Need one format ≥80% syntax valid AND manual fidelity ≥4/5 on ≥2 procedures.",
            "- **web_test integration remains OFF until confirmed.**",
            "",
            f"Full JSON: `{json_path.name}`",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nReport: {json_path}")
    print(f"Markdown: {md_path}")
    for f in formats:
        s = report["summary"][f]
        print(f"  {f}: {s['valid']}/{s['total']} valid ({s['valid_pct']}%)")
    return 0


def _ext(fmt: str) -> str:
    return {
        "mermaid": "mmd",
        "dot": "dot",
        "plantuml": "puml",
        "svg": "svg",
        "html": "html",
        "json_graph": "json",
    }.get(fmt, "txt")


if __name__ == "__main__":
    raise SystemExit(main())
