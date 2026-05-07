#!/usr/bin/env python3
"""
Architecture diagrams for gemma-test — rendered with Manim Community Edition.

Install (prefer a venv; on Windows, Manim may need extra deps — see https://docs.manim.community/)::

    pip install manim

Render previews (low quality, fast)::

    manim -ql scripts/manim_gemma_architecture.py FileSystemRundown
    manim -ql scripts/manim_gemma_architecture.py FullSystemMap

High quality::

    manim -qh scripts/manim_gemma_architecture.py FullSystemMap

Output: ``media/videos/<quality>/<scene>/<Scene>.mp4`` under the current working directory
(usually repo root when you run manim from there).
"""
from __future__ import annotations

from manim import (
    BLUE,
    DOWN,
    FadeIn,
    GREEN,
    LaggedStart,
    LEFT,
    ORANGE,
    RED,
    RIGHT,
    Scene,
    Text,
    UP,
    VGroup,
    WHITE,
    Write,
    Arrow,
    SurroundingRectangle,
    Create,
    ORIGIN,
)

_GREY_TXT = "#ACACAC"


def _caption(text: str, font_size: int = 20) -> Text:
    cap = Text(text, font_size=font_size, color=_GREY_TXT)
    cap.to_edge(DOWN, buff=0.25)
    return cap


class FileSystemRundown(Scene):
    """How folders under the repo relate, especially ``data/`` and RAG sources."""

    def construct(self) -> None:
        title = Text("gemma-test - filesystem & RAG sources", font_size=38)
        title.to_edge(UP, buff=0.4)
        self.play(Write(title))

        block = VGroup(
            Text("Repository (high level)", font_size=26, color=BLUE),
            Text("app_config/     →  settings.py + .env (vLLM URL, RAG caps, auth)", font_size=22),
            Text("api/            →  FastAPI entry (main.py, schemas)", font_size=22),
            Text("core/           →  pipeline, llm, documents, persistence, security, …", font_size=22),
            Text("web_test/       →  React chat UI → build to web_test/dist/", font_size=22),
            Text("admin_site/     →  static admin dashboard (served at /admin)", font_size=22),
            Text("scripts/        →  deploy, export_sop_to_md, vLLM helpers", font_size=22),
            Text("", font_size=8),
            Text("data/  (on disk — often gitignored under data/documents/)", font_size=26, color=GREEN),
            Text("documents/<cat>/*.docx     Word originals", font_size=22),
            Text("documents_md/<cat>/*.md    preferred for RAG (exported Markdown)", font_size=22),
            Text("documents_txt/<cat>/*.txt legacy plain text", font_size=22),
            Text("interactions.db            SQLite: logs + feedback + liked-answer cache", font_size=22),
            Text("", font_size=8),
            Text("Loader order (per category):  .md  →  .txt  →  parse .docx", font_size=22, color=ORANGE),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.22)
        block.next_to(title, DOWN, buff=0.35).align_to(title, LEFT)

        self.play(LaggedStart(*[FadeIn(line, shift=0.08 * UP) for line in block], lag_ratio=0.06))
        cap = _caption(
            "Caption: DocStore (core/documents.py) indexes whichever source wins; "
            "docx_to_md + sop_text_clean shape text before BM25 / inject."
        )
        self.play(FadeIn(cap))
        self.wait(2.5)


class FullSystemMap(Scene):
    """Runtime: browser ↔ API ↔ policy/RAG ↔ vLLM, plus admin & data paths."""

    def construct(self) -> None:
        t = Text("End-to-end system map", font_size=40)
        t.to_edge(UP, buff=0.35)
        self.play(Write(t))

        browser = Text("Browser\nchat UI + admin", font_size=22)
        api = Text(
            "FastAPI :8000\napi/main.py\nauth · rate limit\nstatic / + /admin",
            font_size=20,
        )
        pipe = Text("GemmaPipeline\ncore/pipeline.py", font_size=20)
        pol = Text(
            "chat_policy.py\nlang · profanity\nretrieval anchor",
            font_size=18,
            color=BLUE,
        )
        rag = Text(
            "DocStore\nBM25 or inject-all\n(documents_md / txt / docx)",
            font_size=18,
            color=GREEN,
        )
        llm = Text("GemmaModel\ncore/llm.py\nSYSTEM_PROMPT + RAG block", font_size=20)
        vllm = Text("vLLM :8002\nOpenAI API\nstart_vllm.sh", font_size=20, color=ORANGE)
        sql = Text("SQLite\ninteractions +\nliked cache", font_size=18, color=RED)
        disk = Text("data/\n.md · .txt · .docx", font_size=18, color=_GREY_TXT)

        browser.move_to(UP * 2.2 + LEFT * 0.2)
        api.move_to(UP * 1.0)
        pipe.move_to(UP * 0.05)
        pol.move_to(LEFT * 4.2 + DOWN * 0.6)
        rag.move_to(RIGHT * 4.0 + DOWN * 0.6)
        llm.move_to(DOWN * 1.25)
        vllm.move_to(DOWN * 2.65)
        sql.move_to(LEFT * 5.2 + DOWN * 2.0)
        disk.move_to(RIGHT * 5.0 + DOWN * 2.0)

        nodes = VGroup(browser, api, pipe, pol, rag, llm, vllm, sql, disk)
        for n in nodes:
            self.play(FadeIn(n, scale=0.9))
        self.wait(0.3)

        a1 = Arrow(browser.get_bottom(), api.get_top(), buff=0.15, color=WHITE)
        a2 = Arrow(api.get_bottom(), pipe.get_top(), buff=0.15, color=WHITE)
        a3 = Arrow(pipe.get_left() + DOWN * 0.1, pol.get_top() + RIGHT * 0.3, buff=0.1, color=BLUE)
        a4 = Arrow(pipe.get_right() + DOWN * 0.1, rag.get_top() + LEFT * 0.2, buff=0.1, color=GREEN)
        a5 = Arrow(pipe.get_bottom(), llm.get_top(), buff=0.1, color=WHITE)
        a6 = Arrow(llm.get_bottom(), vllm.get_top(), buff=0.1, color=ORANGE)
        a7 = Arrow(api.get_bottom() + LEFT * 1.2, sql.get_top() + RIGHT * 0.2, buff=0.08, color=RED)
        a8 = Arrow(rag.get_bottom(), disk.get_top(), buff=0.08, color=_GREY_TXT)

        self.play(
            *[Create(x) for x in (a1, a2, a3, a4, a5, a6, a7, a8)],
            run_time=1.8,
        )

        cap = _caption(
            "Caption: POST /chat → policy checks → RAG context appended to system prompt → "
            "httpx POST to vLLM; /admin/git-refresh reloads git + DocStore only (no vLLM restart)."
        )
        self.play(FadeIn(cap))
        self.wait(3)


class FullSystemMapWithFrames(Scene):
    """Same as FullSystemMap but boxes around groups (optional eye candy)."""

    def construct(self) -> None:
        t = Text("Components (boxed)", font_size=36)
        t.to_edge(UP, buff=0.35)
        self.play(Write(t))

        client = VGroup(
            Text("Client", font_size=24, color=BLUE),
            Text("web_test/", font_size=20),
            Text("admin_site/", font_size=20),
        ).arrange(DOWN, buff=0.15)

        server = VGroup(
            Text("API server", font_size=24, color=GREEN),
            Text("FastAPI + GemmaPipeline", font_size=20),
            Text("DocStore · SQLite · policies", font_size=18, color=_GREY_TXT),
        ).arrange(DOWN, buff=0.15)

        infer = VGroup(
            Text("Inference", font_size=24, color=ORANGE),
            Text("vLLM pod :8002", font_size=20),
        ).arrange(DOWN, buff=0.15)

        client.move_to(LEFT * 4.5 + DOWN * 0.2)
        server.move_to(ORIGIN)
        infer.move_to(RIGHT * 4.5 + DOWN * 0.2)

        b1 = SurroundingRectangle(client, color=BLUE, buff=0.2)
        b2 = SurroundingRectangle(server, color=GREEN, buff=0.2)
        b3 = SurroundingRectangle(infer, color=ORANGE, buff=0.2)

        self.play(FadeIn(client), Create(b1))
        self.play(FadeIn(server), Create(b2))
        self.play(FadeIn(infer), Create(b3))

        arr1 = Arrow(client.get_right(), server.get_left(), buff=0.1)
        arr2 = Arrow(server.get_right(), infer.get_left(), buff=0.1)
        self.play(Create(arr1), Create(arr2))

        cap = _caption(
            "Caption: Static files from web_test/dist and admin_site are served by the same "
            "FastAPI app; inference is always a separate HTTP service on port 8002."
        )
        self.play(FadeIn(cap))
        self.wait(2.5)
