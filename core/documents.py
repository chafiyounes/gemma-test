"""Category-aware document loader + BM25 retrieval.

Layout:
    data/documents/<Category>/*.docx

Each first-level subdirectory of data/documents/ is treated as a CATEGORY.
A query targets a specific category; the top-k matching docs are returned.
Files placed directly in data/documents/ (without a subfolder) are ignored.
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "data" / "documents"

_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ0-9\u0600-\u06FF]+", re.UNICODE)


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _read_docx(path: Path) -> str:
    try:
        from docx import Document  # type: ignore
        doc = Document(str(path))
        parts = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text and cell.text.strip():
                        parts.append(cell.text.strip())
        return "\n".join(parts)
    except Exception:
        try:
            import xml.etree.ElementTree as ET
            import zipfile
            with zipfile.ZipFile(path) as zf:
                with zf.open("word/document.xml") as f:
                    tree = ET.parse(f)
            return "\n".join(t.text for t in tree.iter() if t.tag.endswith("}t") and t.text)
        except Exception as exc:
            logger.warning("Could not read %s: %s", path.name, exc)
            return ""


@dataclass
class Doc:
    name: str
    category: str
    text: str
    tokens: List[str]
    tf: Counter


@dataclass
class CategoryIndex:
    name: str
    docs: List[Doc]
    df: Counter
    avgdl: float


class DocStore:
    """Per-category BM25 index. Each subfolder of data/documents/ is a category."""

    def __init__(self, docs_dir: Path = DOCS_DIR):
        self.docs_dir = docs_dir
        self.indexes: Dict[str, CategoryIndex] = {}
        self._load()

    def _load(self) -> None:
        if not self.docs_dir.is_dir():
            logger.warning("Documents dir not found: %s", self.docs_dir)
            return

        for sub in sorted(self.docs_dir.iterdir()):
            if not sub.is_dir():
                continue
            cat_name = sub.name
            files = sorted(sub.glob("*.docx"))
            docs: List[Doc] = []
            df: Counter = Counter()
            total_len = 0
            for p in files:
                text = _read_docx(p)
                if not text.strip():
                    continue
                toks = _tokenize(text)
                if not toks:
                    continue
                tf = Counter(toks)
                docs.append(Doc(name=p.stem, category=cat_name, text=text, tokens=toks, tf=tf))
                for term in tf:
                    df[term] += 1
                total_len += len(toks)
            if docs:
                self.indexes[cat_name] = CategoryIndex(
                    name=cat_name,
                    docs=docs,
                    df=df,
                    avgdl=total_len / len(docs),
                )
                logger.info("DocStore: category '%s' loaded %d docs", cat_name, len(docs))
            else:
                logger.warning("DocStore: category '%s' has no readable docs", cat_name)

        if not self.indexes:
            logger.warning("DocStore: no categories loaded from %s", self.docs_dir)

    def list_categories(self) -> List[Dict]:
        return [
            {"name": c.name, "doc_count": len(c.docs), "doc_names": [d.name for d in c.docs]}
            for c in self.indexes.values()
        ]

    def _bm25(self, q_tokens: List[str], doc: Doc, idx: CategoryIndex,
              k1: float = 1.5, b: float = 0.75) -> float:
        N = len(idx.docs)
        dl = len(doc.tokens) or 1
        score = 0.0
        for term in q_tokens:
            df_t = idx.df.get(term, 0)
            if df_t == 0:
                continue
            idf = math.log((N - df_t + 0.5) / (df_t + 0.5) + 1.0)
            f = doc.tf.get(term, 0)
            denom = f + k1 * (1 - b + b * dl / (idx.avgdl or 1))
            score += idf * (f * (k1 + 1)) / (denom or 1)
        return score

    def retrieve(self, query: str, category: Optional[str] = None, k: int = 5) -> List[Doc]:
        if not self.indexes:
            return []
        if category and category in self.indexes:
            targets = [self.indexes[category]]
        else:
            targets = list(self.indexes.values())

        q_tokens = _tokenize(query)
        if not q_tokens:
            return []

        scored = []
        for idx in targets:
            for d in idx.docs:
                s = self._bm25(q_tokens, d, idx)
                if s > 0:
                    scored.append((s, d))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [d for _, d in scored[:k]]

    def build_context(self, query: str, category: Optional[str] = None,
                      k: int = 5, max_chars: int = 14000) -> str:
        top = self.retrieve(query, category=category, k=k)
        if not top:
            return ""
        parts: List[str] = []
        budget = max_chars
        for d in top:
            block = f"### Document : {d.name}  (catégorie : {d.category})\n{d.text.strip()}\n"
            if len(block) > budget:
                block = block[:budget].rsplit("\n", 1)[0] + "\n…(tronqué)"
                parts.append(block)
                break
            parts.append(block)
            budget -= len(block)
        return "\n".join(parts)

    def build_all_docs_context(self, category: Optional[str] = None,
                                max_chars: int = 20000) -> str:
        """Return the full text of ALL documents in a category.

        Unlike build_context() which uses BM25 to pick top-k, this method
        dumps every document so the model always has the complete SOP set.
        """
        if not self.indexes:
            return ""
        if category and category in self.indexes:
            targets = [self.indexes[category]]
        else:
            targets = list(self.indexes.values())

        parts: List[str] = []
        budget = max_chars
        for idx in targets:
            for d in idx.docs:
                block = f"### Document : {d.name}  (catégorie : {d.category})\n{d.text.strip()}\n"
                if len(block) > budget:
                    block = block[:budget].rsplit("\n", 1)[0] + "\n…(tronqué)"
                    parts.append(block)
                    budget = 0
                    break
                parts.append(block)
                budget -= len(block)
            if budget <= 0:
                break
        logger.info("Injected %d documents into context (%d chars)",
                    len(parts), max_chars - budget)
        return "\n".join(parts)


_store: Optional[DocStore] = None


def get_store() -> DocStore:
    global _store
    if _store is None:
        _store = DocStore()
    return _store
