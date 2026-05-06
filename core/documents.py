"""Category-aware document loader + BM25 retrieval.

Layout (either is supported per category):

1. **Preferred — cleaned text exports** (darija-chatbot-style pipeline):
       data/documents_txt/<Category>/*.txt
   Produced by ``python -m scripts.export_sop_to_txt`` from ``.docx`` sources.
   Plain text only: body order preserved, metadata/author tables stripped.

2. **Fallback — Word sources**:
       data/documents/<Category>/*.docx
   Parsed with body-order walking (paragraphs + tables interleaved), same idea
   as ``darija-chatbot/chunking/parser.py`` — not ``doc.paragraphs`` + ``tables``
   (that reorder content and drop context around tables).

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
DOCS_TXT_DIR = REPO_ROOT / "data" / "documents_txt"

_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ0-9\u0600-\u06FF]+", re.UNICODE)

# If hints didn't fire, Darija / mixed messages often have no French lemmas for BM25.
_DARIJA_LEX_BOOST = re.compile(
    r"\b("
    r"bghay|bgha|bghit|bghiti|chno|chnowa|ntebi3|ntebi3ohom|dyal|dial|diali|"
    r"walakin|wakha|katlab|ybdel|ybeddel|flivraison|f\s+livraison"
    r")\b",
    re.IGNORECASE,
)

_HEADER_TABLE_KEYWORDS = {
    "titre", "référence", "reference", "version",
    "date d'application", "date d\u2019application",
    "domaine d'application", "domaine d\u2019application",
    "responsable",
}
_FOOTER_TABLE_KEYWORDS = {
    "rédigé par", "redige par", "réalisé par", "realise par",
    "vérifié par", "verifie par", "approuvé par", "approuve par",
    "validé par", "valide par",
}
_AUTHOR_TEXT_KEYWORDS = [
    "rédigé par", "redige par", "réalisé par", "realise par",
    "vérifié par", "verifie par", "approuvé par", "approuve par",
    "validé par", "valide par",
]


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


# BM25 is lexical: French/Darija questions may miss French SOP terms unless we
# append French synonyms. **English questions must stay English-only** (no
# French keyword stuffing) — rely on normal English terms + full-category inject.
_LOGISTICS_EN_FR: tuple[tuple[str, str], ...] = (
    ("delivery", "livraison livrer livraisons"),
    ("deliver", "livrer livraison"),
    ("region", "région destination villes zone couverture"),
    ("vendor", "vendeur vendeurs"),
    ("customer", "client clients client final"),
    ("refund", "remboursement"),
    ("damaged", "endommagé dommage incident transport"),
    ("pickup", "ramassage collecte pickup"),
    ("verification", "vérification vérifier"),
    ("verify", "vérifier"),
    ("system", "système plateforme"),
    ("does not appear", "n'apparaît pas n'apparaissent pas"),
    ("specific", "spécifique"),
    ("asking if", "question demande"),
    ("final client", "client final"),
    ("phone", "téléphone téléphone coordonnées client contact"),
    ("mobile", "téléphone portable contact client"),
    ("number", "numéro téléphone contact client coordonnées"),
    ("change", "modification changement coordonnées procédure"),
    ("update", "mise à jour modification changement coordonnées"),
)


# Extra BM25 terms when the query is already in French (or Darija + French lexique).
_LOGISTICS_FR_HINTS: tuple[tuple[str, str], ...] = (
    ("distribué", "statut colis livré réception livraison"),
    ("injoignable", "tentative livraison livreur contact inaccessible"),
    ("retour en cours", "retour colis entrepôt expéditeur statut"),
    ("retour à l'entrepôt", "retour entrepôt colis statut"),
    ("en attente de retour", "retour colis retour expéditeur"),
    ("facturé", "facture facturation statut"),
    ("facture", "facturation statut comptabilité"),
    ("remboursement", "rembourser validation client final montant remboursement"),
    ("rembourser", "remboursement procédure colis"),
    ("endommagé", "dommage colis incident photo constat déclaration"),
    ("fragile", "emballage responsabilité transport dommage"),
    ("adresse", "modification destination livraison changement"),
    ("destination", "adresse ville modification livraison"),
    ("téléphone", "contact téléphone client ramassage"),
    ("telephone", "téléphone coordonnées client contact modification livraison"),
    ("numéro", "téléphone contact client modification"),
    ("numero", "téléphone contact client modification"),
    ("supprimer", "annulation suppression colis annuler"),
    ("annuler", "annulation colis statut"),
    ("à préparer", "stock entrepôt préparation colis"),
    ("ramassage", "collecte pickup programmé demande ramassage"),
    ("ramassé", "colis statut annulation suppression annuler ramassage"),
    ("liste des villes", "couverture zone destination livrable"),
    ("plateforme", "assistance documentation tutoriel procédure"),
    ("aide", "assistance centre d'aide documentation SENDIT"),
    ("hors casablanca", "transport zone hub dommage responsabilité"),
    ("200 dh", "seuil validation remboursement montant dirhams"),
    ("livraison", "colis en cours tournée livreur statut modification coordonnées"),
    ("modifier", "modification changement coordonnées client procédure"),
    ("changement", "modification coordonnées téléphone adresse client"),
    ("coordonnées", "contact téléphone adresse client modification livraison"),
    ("coordonnees", "contact téléphone adresse client modification livraison"),
    ("déjà", "colis déjà statut livraison en cours tournée livreur"),
    ("deja", "colis statut livraison en cours tournée"),
)


def expand_query_for_retrieval_fr_darija(query: str) -> str:
    """Broaden BM25 recall: French/Darija hints + English→FR lemmas when EN terms match.

    English stays **without** blind French stuffing: only `_LOGISTICS_EN_FR` adds
    French when matching English substrings are present (vendor, delivery, …).
    """
    low = (query or "").lower()
    extra: List[str] = []
    for en, fr in _LOGISTICS_EN_FR:
        if en in low:
            extra.append(fr)
    for trigger, fr in _LOGISTICS_FR_HINTS:
        if trigger in low:
            extra.append(fr)
    if not extra and _DARIJA_LEX_BOOST.search(query or ""):
        extra.append(
            "livraison colis client téléphone coordonnées modification vendeur procédure"
        )
    if not extra:
        return query
    return f"{query}\n{' '.join(extra)}"


def _collapse_ws(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def condense_sop_plaintext(text: str) -> str:
    """Tighter plain text for RAG: normalize newlines and spacing (no semantic summarization)."""
    if not text:
        return ""
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = _collapse_ws(t)
    return t


def _strip_image_markers(text: str) -> str:
    """Remove help-center style image placeholders; keep plain SOP text."""
    text = re.sub(r"\[\[IMAGE:[^\]]+\]\]", "", text, flags=re.IGNORECASE)
    return _collapse_ws(text)


def strip_author_table_from_plain_text(text: str) -> str:
    """Remove trailing markdown-style author/validation tables (darija-chatbot grouper idea)."""
    lines = text.split("\n")
    result: List[str] = []
    table_block: List[str] = []
    in_table = False

    for line in lines:
        if line.strip().startswith("|"):
            in_table = True
            table_block.append(line)
        else:
            if in_table:
                block_lower = "\n".join(table_block).lower()
                if any(kw in block_lower for kw in _AUTHOR_TEXT_KEYWORDS):
                    pass  # drop
                else:
                    result.extend(table_block)
                table_block = []
                in_table = False
            result.append(line)
    if in_table and table_block:
        block_lower = "\n".join(table_block).lower()
        if not any(kw in block_lower for kw in _AUTHOR_TEXT_KEYWORDS):
            result.extend(table_block)
    return _collapse_ws("\n".join(result))


def _table_to_markdown(table_xml) -> str:
    from docx.oxml.ns import qn

    rows = table_xml.findall(qn("w:tr"))
    if not rows:
        return ""

    parsed_rows: List[List[str]] = []
    for row in rows:
        cells = row.findall(qn("w:tc"))
        cell_texts = []
        for cell in cells:
            text = "".join(node.text or "" for node in cell.iter(qn("w:t"))).strip()
            cell_texts.append(text)
        parsed_rows.append(cell_texts)

    if not parsed_rows:
        return ""

    headers = parsed_rows[0]
    data_rows = parsed_rows[1:]
    col_widths: List[int] = []
    for i, h in enumerate(headers):
        max_w = len(h)
        for r in data_rows:
            if i < len(r):
                max_w = max(max_w, len(r[i]))
        col_widths.append(max(max_w, 3))

    lines: List[str] = []
    lines.append("| " + " | ".join(h.ljust(w) for h, w in zip(headers, col_widths)) + " |")
    lines.append("| " + " | ".join("-" * w for w in col_widths) + " |")
    for row in data_rows:
        padded = []
        for i, w in enumerate(col_widths):
            val = row[i] if i < len(row) else ""
            padded.append(val.ljust(w))
        lines.append("| " + " | ".join(padded) + " |")
    return "\n".join(lines)


def _is_metadata_markdown_table(md: str) -> bool:
    """Detect SOP header/footer tables from first-column keywords (darija-chatbot)."""
    lines = [ln for ln in md.splitlines() if ln.strip().startswith("|")]
    if len(lines) < 2:
        return False
    first_cols: List[str] = []
    for ln in lines:
        parts = [p.strip() for p in ln.strip().strip("|").split("|")]
        if parts:
            first_cols.append(parts[0].lower())
    all_kw = _HEADER_TABLE_KEYWORDS | _FOOTER_TABLE_KEYWORDS
    matches = sum(1 for v in first_cols if v in all_kw)
    return matches >= 2 or (bool(first_cols) and matches / len(first_cols) >= 0.5)


def _read_docx_ordered(path: Path) -> str:
    """Walk ``word/document.xml`` body order: paragraphs + tables (darija-chatbot style)."""
    try:
        from docx import Document
        from docx.oxml.ns import qn
    except ImportError:
        logger.warning("python-docx not installed; cannot read %s", path.name)
        return ""

    try:
        doc = Document(str(path))
        body = doc.element.body
        chunks: List[str] = []
        for child in body:
            tag = child.tag.split("}")[-1]
            if tag == "p":
                text = "".join(node.text or "" for node in child.iter(qn("w:t"))).strip()
                if text:
                    chunks.append(text)
            elif tag == "tbl":
                md = _table_to_markdown(child)
                if md and not _is_metadata_markdown_table(md):
                    chunks.append(md)
        raw = "\n\n".join(chunks)
        raw = strip_author_table_from_plain_text(raw)
        return _strip_image_markers(raw)
    except Exception as exc:
        logger.warning("Ordered docx read failed for %s: %s", path.name, exc)
        return ""


def _read_txt(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
        text = strip_author_table_from_plain_text(text)
        return _strip_image_markers(text)
    except Exception as exc:
        logger.warning("Could not read %s: %s", path.name, exc)
        return ""


def _read_docx(path: Path) -> str:
    """Backward-compatible name: ordered parse, no paragraph/table split."""
    text = _read_docx_ordered(path)
    if text:
        return text
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

    def __init__(self, docs_dir: Path = DOCS_DIR, docs_txt_dir: Path = DOCS_TXT_DIR):
        self.docs_dir = docs_dir
        self.docs_txt_dir = docs_txt_dir
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
            txt_cat = self.docs_txt_dir / cat_name
            use_txt = txt_cat.is_dir() and any(txt_cat.glob("*.txt"))
            if use_txt:
                files = sorted(txt_cat.glob("*.txt"))
                reader = _read_txt
            else:
                files = sorted(sub.glob("*.docx"))
                reader = _read_docx
            docs: List[Doc] = []
            df: Counter = Counter()
            total_len = 0
            for p in files:
                text = reader(p)
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
                logger.info(
                    "DocStore: category '%s' loaded %d docs (%s)",
                    cat_name,
                    len(docs),
                    "documents_txt" if use_txt else "docx",
                )
                if not use_txt:
                    logger.warning(
                        "DocStore: category '%s' — consider `data/documents_txt/%s/*.txt` for condensed plain-text RAG",
                        cat_name,
                        cat_name,
                    )
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

    def category_corpus_chars(self, category: str) -> int:
        idx = self.indexes.get(category)
        if not idx:
            return 0
        return sum(len(d.text) for d in idx.docs)

    def retrieve(
        self,
        query: str,
        category: Optional[str] = None,
        k: int = 5,
        *,
        expand_fr_darija_hints: bool = False,
    ) -> List[Doc]:
        if not self.indexes:
            return []
        if expand_fr_darija_hints:
            query = expand_query_for_retrieval_fr_darija(query)
        if category and category in self.indexes:
            targets = [self.indexes[category]]
        else:
            targets = list(self.indexes.values())

        q_tokens = _tokenize(query)
        if not q_tokens:
            fallback_nt: List[Doc] = []
            for idx in targets:
                for d in idx.docs:
                    fallback_nt.append(d)
                    if len(fallback_nt) >= k:
                        return fallback_nt[:k]
            return fallback_nt

        scored = []
        for idx in targets:
            for d in idx.docs:
                s = self._bm25(q_tokens, d, idx)
                if s > 0:
                    scored.append((s, d))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = [d for _, d in scored[:k]]
        if out:
            return out
        # Query terms missed the lexicon (scripts, typos): still return *some* docs.
        fallback: List[Doc] = []
        for idx in targets:
            for d in idx.docs:
                fallback.append(d)
                if len(fallback) >= k:
                    return fallback[:k]
        return fallback

    def _rank_docs_in_index(
        self,
        idx: CategoryIndex,
        query: str,
        *,
        expand_for_retrieval: bool,
    ) -> List[Doc]:
        """Stable sort: BM25 score desc, then original file order."""
        q = expand_query_for_retrieval_fr_darija(query) if expand_for_retrieval else query
        q_tokens = _tokenize(q)
        if not q_tokens:
            return list(idx.docs)
        scored: List[tuple[float, int, Doc]] = []
        for i, d in enumerate(idx.docs):
            s = self._bm25(q_tokens, d, idx)
            scored.append((s, i, d))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [t[2] for t in scored]

    def build_context(
        self,
        query: str,
        category: Optional[str] = None,
        k: int = 5,
        max_chars: int = 14000,
        *,
        expand_fr_darija_hints: bool = False,
        condense: bool = False,
    ) -> str:
        top = self.retrieve(
            query, category=category, k=k, expand_fr_darija_hints=expand_fr_darija_hints
        )
        if not top:
            return ""
        parts: List[str] = []
        budget = max_chars
        for d in top:
            body = condense_sop_plaintext(d.text) if condense else d.text.strip()
            block = f"### Document : {d.name}  (catégorie : {d.category})\n{body}\n"
            if len(block) > budget:
                block = block[:budget].rsplit("\n", 1)[0] + "\n…(tronqué)"
                parts.append(block)
                break
            parts.append(block)
            budget -= len(block)
        return "\n".join(parts)

    def build_all_docs_context(
        self,
        category: Optional[str] = None,
        max_chars: int = 15000,
        *,
        query: Optional[str] = None,
        expand_for_retrieval: bool = False,
        condense: bool = False,
    ) -> str:
        """Concatenate **all** documents in a category up to *max_chars*.

        Every document in the category appears at least once (header + body slice).
        When the total condensed corpus exceeds *max_chars*, body text is split
        **proportionally** across documents so none are dropped entirely.
        Prefer ``condense=True`` (plain-text tightening) to fit more content.
        """
        if not self.indexes:
            return ""
        if category and category in self.indexes:
            targets = [self.indexes[category]]
        else:
            targets = list(self.indexes.values())

        parts: List[str] = []
        used = 0
        for idx in targets:
            docs = (
                self._rank_docs_in_index(idx, query, expand_for_retrieval=expand_for_retrieval)
                if (query and query.strip())
                else list(idx.docs)
            )
            if not docs:
                continue
            n = len(docs)
            entries: List[tuple[str, str, str]] = []
            for d in docs:
                body = condense_sop_plaintext(d.text) if condense else d.text.strip()
                header = f"### Document : {d.name}  (catégorie : {d.category})\n"
                entries.append((header, body, d.name))

            # Separator between doc blocks: single newline after body
            overhead = sum(len(h) + 1 for h, _, _ in entries)
            budget_bodies = max(0, max_chars - overhead - max(0, n - 1))
            total_body = sum(len(b) for _, b, _ in entries)

            if total_body == 0:
                for header, _, _name in entries:
                    parts.append(header + "\n")
                continue

            if total_body <= budget_bodies:
                for header, body, _name in entries:
                    block = header + body + "\n"
                    parts.append(block)
                    used += len(block)
                continue

            ratios = [len(b) / total_body for _, b, _ in entries]
            raw_alloc = [int(budget_bodies * r) for r in ratios]
            alloc = raw_alloc
            diff = budget_bodies - sum(alloc)
            if diff != 0 and alloc:
                alloc[-1] = max(0, alloc[-1] + diff)

            for i, (header, body, _name) in enumerate(entries):
                cap = alloc[i] if i < len(alloc) else 0
                if len(body) <= cap:
                    chunk = body
                    suffix = "\n"
                else:
                    chunk = body[:cap].rsplit("\n", 1)[0] if cap > 80 else body[:cap]
                    chunk = chunk or body[:cap]
                    suffix = "\n…(tronqué — voir source .txt complète)\n"
                block = header + chunk + suffix
                parts.append(block)
                used += len(block)

        logger.info(
            "Injected %d document blocks into context (~%d chars of %d budget, condense=%s)",
            len(parts),
            used,
            max_chars,
            condense,
        )
        return "\n".join(parts)


_store: Optional[DocStore] = None


def get_store() -> DocStore:
    global _store
    if _store is None:
        _store = DocStore()
    return _store
