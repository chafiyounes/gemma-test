#!/usr/bin/env python3
"""
Structured architecture diagrams for gemma-test (Manim Community Edition).

The scenes are intentionally top-down:
1) Big categories
2) Subsystems under each category
3) Connections / data flow
4) Bottom caption

Render examples:
    python -m manim -ql scripts/manim_gemma_architecture.py RepoTopDownMap
    python -m manim -ql scripts/manim_gemma_architecture.py SystemTopDownMap
"""
from __future__ import annotations

from manim import (
    BLUE,
    DOWN,
    FadeIn,
    GREEN,
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
)

GREY_TXT = "#ACACAC"
TITLE_SIZE = 38
BOX_TITLE_SIZE = 24
ITEM_SIZE = 19
CAPTION_SIZE = 19


def _caption(text: str) -> Text:
    c = Text(text, font_size=CAPTION_SIZE, color=GREY_TXT)
    c.to_edge(DOWN, buff=0.24)
    return c


def _labeled_box(title: str, lines: list[str], color) -> VGroup:
    head = Text(title, font_size=BOX_TITLE_SIZE, color=color)
    items = VGroup(*[Text(line, font_size=ITEM_SIZE) for line in lines]).arrange(
        DOWN, aligned_edge=LEFT, buff=0.13
    )
    body = VGroup(head, items).arrange(DOWN, aligned_edge=LEFT, buff=0.16)
    frame = SurroundingRectangle(body, color=color, buff=0.22)
    return VGroup(frame, body)


class RepoTopDownMap(Scene):
    """Top-down repo structure: categories -> modules -> data folders."""

    def construct(self) -> None:
        title = Text("gemma-test repository - top-down map", font_size=TITLE_SIZE)
        title.to_edge(UP, buff=0.3)
        self.play(Write(title))

        app_box = _labeled_box(
            "Application Layer",
            [
                "api/        FastAPI routes and schemas",
                "core/       pipeline, llm, policy, RAG, DB",
                "app_config/ settings and environment",
            ],
            BLUE,
        )
        ui_box = _labeled_box(
            "Presentation Layer",
            [
                "web_test/   React chat frontend (build -> dist)",
                "admin_site/ admin dashboard (served at /admin)",
            ],
            GREEN,
        )
        data_box = _labeled_box(
            "Data and Documents",
            [
                "data/documents/<cat>/*.docx   source Word files",
                "data/documents_md/<cat>/*.md  preferred RAG source",
                "data/documents_txt/<cat>/*.txt legacy source",
                "data/interactions.db          SQLite logs/feedback/cache",
            ],
            ORANGE,
        )
        ops_box = _labeled_box(
            "Operations and Tooling",
            [
                "scripts/start_vllm.sh, start_api.sh",
                "scripts/deploy_runner.py, restart_api.sh",
                "scripts/export_sop_to_md.py, rag_audit.py",
            ],
            RED,
        )

        app_box.move_to(LEFT * 4.25 + UP * 1.1)
        ui_box.move_to(RIGHT * 3.9 + UP * 1.15)
        data_box.move_to(LEFT * 4.1 + DOWN * 1.65)
        ops_box.move_to(RIGHT * 3.9 + DOWN * 1.65)

        self.play(FadeIn(app_box, shift=UP * 0.15), FadeIn(ui_box, shift=UP * 0.15))
        self.play(FadeIn(data_box, shift=DOWN * 0.15), FadeIn(ops_box, shift=DOWN * 0.15))

        a1 = Arrow(app_box.get_bottom(), data_box.get_top(), buff=0.18, color=WHITE)
        a2 = Arrow(ui_box.get_left(), app_box.get_right(), buff=0.18, color=WHITE)
        a3 = Arrow(ops_box.get_left(), app_box.get_right() + DOWN * 0.35, buff=0.12, color=WHITE)
        a4 = Arrow(ops_box.get_left() + UP * 0.3, data_box.get_right(), buff=0.16, color=WHITE)
        self.play(Create(a1), Create(a2), Create(a3), Create(a4), run_time=1.8)

        cap = _caption(
            "Caption: loader order for RAG is documents_md -> documents_txt -> docx parse; "
            "scripts drive export/deploy while API/core serve runtime."
        )
        self.play(FadeIn(cap))
        self.wait(2.6)


class SystemTopDownMap(Scene):
    """Top-down runtime architecture with category->component breakdown."""

    def construct(self) -> None:
        title = Text("Runtime architecture - top-down", font_size=TITLE_SIZE)
        title.to_edge(UP, buff=0.3)
        self.play(Write(title))

        client_box = _labeled_box(
            "1) Client Surfaces",
            ["Browser chat UI", "Browser admin UI"],
            BLUE,
        )
        api_box = _labeled_box(
            "2) API Layer (:8000)",
            ["Auth + rate limit", "/chat and /admin routes", "Static serving"],
            GREEN,
        )
        app_box = _labeled_box(
            "3) Application Core",
            ["GemmaPipeline", "chat_policy checks", "DocStore retrieval", "GemmaModel prompt build"],
            ORANGE,
        )
        infer_box = _labeled_box(
            "4) Inference Layer (:8002)",
            ["vLLM OpenAI-compatible endpoint", "POST /v1/chat/completions"],
            RED,
        )
        state_box = _labeled_box(
            "5) Persistent State",
            ["SQLite interactions/feedback/liked-cache", "documents_md/txt/docx category files"],
            "#B46CFF",
        )

        client_box.move_to(UP * 1.8)
        api_box.move_to(UP * 0.7)
        app_box.move_to(DOWN * 0.55)
        infer_box.move_to(DOWN * 1.85 + LEFT * 3.0)
        state_box.move_to(DOWN * 1.85 + RIGHT * 3.2)

        self.play(FadeIn(client_box, shift=UP * 0.12))
        self.play(FadeIn(api_box, shift=UP * 0.08))
        self.play(FadeIn(app_box, shift=DOWN * 0.08))
        self.play(FadeIn(infer_box, shift=LEFT * 0.12), FadeIn(state_box, shift=RIGHT * 0.12))

        flow1 = Arrow(client_box.get_bottom(), api_box.get_top(), buff=0.14, color=WHITE)
        flow2 = Arrow(api_box.get_bottom(), app_box.get_top(), buff=0.14, color=WHITE)
        flow3 = Arrow(app_box.get_bottom() + LEFT * 1.05, infer_box.get_top(), buff=0.12, color=WHITE)
        flow4 = Arrow(app_box.get_bottom() + RIGHT * 1.05, state_box.get_top(), buff=0.12, color=WHITE)
        flow5 = Arrow(state_box.get_left() + UP * 0.35, app_box.get_right(), buff=0.12, color=WHITE)
        self.play(Create(flow1), Create(flow2), Create(flow3), Create(flow4), Create(flow5), run_time=2.0)

        cap = _caption(
            "Caption: request path is Client -> API -> Core -> vLLM, while state is read/written in "
            "parallel; admin git-refresh reloads DocStore without touching vLLM."
        )
        self.play(FadeIn(cap))
        self.wait(2.8)
