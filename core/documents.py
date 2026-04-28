"""Document loader + lightweight BM25-style retrieval for SOP context injection.

All .docx files under data/documents/ are loaded at module import time.
Provides `retrieve(query, k=5)` returning the top-k most relevant chunks.
No external embedding model — pure lexical scoring (fast, zero deps beyond python-docx).
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# Default location: <repo>/data/documents
REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "data" / "documents"

# Tokenization keeps Latin letters, digits, and Arabic letters
_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ0-9\u0600-\u06FF]+", re.UNICODE)


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _read_docx(path: Path) -> str:
    """Extract plain text from a .docx using python-docx; fallback to zipfile/xml."""
    try:
        from docx import Document  # type: ignore

        doc = Document(str(path))
        parts: List[str] = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text and cell.text.strip():
                        parts.append(cell.text.strip())
        return "\n".join(parts)
    except Exception:
        # Fallback: parse the underlying XML directly
        try:
            import xml.etree.ElementTree as ET
            import zipfile

            with zipfile.ZipFile(path) as zf:
                with zf.open("word/document.xml") as f:
                    tree = ET.parse(f)
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            texts = [t.text for t in tree.iter() if t.tag.endswith("}t") and t.text]
            return "\n".join(texts)
        except Exception as exc:
            logger.warning("Could not read %s: %s", path.name, exc)
            return ""


@dataclass
class Doc:
    name: str
    text: str
    tokens: List[str]
    tf: Counter


class DocStore:
    """Loads docs once; provides BM25-lite retrieval."""

    def __init__(self, docs_dir: Path = DOCS_DIR):
        self.docs_dir = docs_dir
        self.docs: List[Doc] = []
        self.df: Counter = Counter()  # document frequency
        self.avgdl: float = 0.0
        self._load()

    def _load(self) -> None:
        if not self.docs_dir.is_dir():
            logger.warning("Documents dir not found: %s", self.docs_dir)
            return
        files = sorted(self.docs_dir.glob("*.docx"))
        total_len = 0
        for p in files:
            text = _read_docx(p)
            if not text.strip():
                continue
            toks = _tokenize(text)
            if not toks:
                continue
            tf = Counter(toks)
            self.docs.append(Doc(name=p.stem, text=text, tokens=toks, tf=tf))
            for term in tf.keys():
                self.df[term] += 1
            total_len += len(toks)
        if self.docs:
            self.avgdl = total_len / len(self.docs)
            logger.info(
                "DocStore loaded %d docs (avg %d tokens) from %s",
                len(self.docs),
                int(self.avgdl),
                self.docs_dir,
            )
        else:
            logger.warning("No .docx documents loaded from %s", self.docs_dir)

    def _bm25_score(self, q_tokens: List[str], doc: Doc, k1: float = 1.5, b: float = 0.75) -> float:
        if not self.docs:
            return 0.0
        N = len(self.docs)
        dl = len(doc.tokens) or 1
        score = 0.0
        for term in q_tokens:
            df = self.df.get(term, 0)
            if df == 0:
                continue
            idf = math.log((N - df + 0.5) / (df + 0.5) + 1.0)
            f = doc.tf.get(term, 0)
            denom = f + k1 * (1 - b + b * dl / (self.avgdl or 1))
            score += idf * (f * (k1 + 1)) / (denom or 1)
        return score

    def retrieve(self, query: str, k: int = 5) -> List[Doc]:
        if not self.docs:
            return []
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []
        scored = [(self._bm25_score(q_tokens, d), d) for d in self.docs]
        scored = [(s, d) for s, d in scored if s > 0]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [d for _, d in scored[:k]]

    def build_context(self, query: str, k: int = 5, max_chars: int = 12000) -> str:
        """Return a formatted context block from the top-k docs (truncated to max_chars)."""
        top = self.retrieve(query, k=k)
        if not top:
            return ""
        out_parts: List[str] = []
        budget = max_chars
        for d in top:
            block = f"### Document: {d.name}\n{d.text.strip()}\n"
            if len(block) > budget:
                block = block[:budget].rsplit("\n", 1)[0] + "\n…(truncated)"
                out_parts.append(block)
                break
            out_parts.append(block)
            budget -= len(block)
        return "\n".join(out_parts)


# Module-level singleton (lazily built on first use)
_store: Optional[DocStore] = None


def get_store() -> DocStore:
    global _store
    if _store is None:
        _store = DocStore()
    return _store
