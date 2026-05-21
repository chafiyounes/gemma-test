import { Fragment, lazy, Suspense } from "react";
import { getApiUrl } from "../services/api";

const MermaidDiagram = lazy(() => import("../components/MermaidDiagram"));

export function resolveDocImageSrc(src) {
  if (!src) return src;
  const s = src.trim();
  if (/^https?:\/\//i.test(s)) return s;
  const base = getApiUrl().replace(/\/+$/, "");
  const path = s.startsWith("/") ? s : `/api/rag-media/${s.replace(/^\.?\//, "")}`;
  return `${base}${path}`;
}

export function resolveDocHref(href) {
  if (!href) return href;
  const h = href.trim();
  if (/^https?:\/\//i.test(h)) return h;
  return resolveDocImageSrc(h);
}

/** True if URL/path looks like a raster or SVG asset served as an image. */
export function isImagePath(href) {
  if (!href) return false;
  return /\.(png|jpe?g|gif|webp|svg)(\?|#|$)/i.test(href.trim());
}

/** Normalize a single source hint for display (strip brackets and citation numbers). */
export function formatSourceHint(text) {
  if (!text) return "";
  let s = text.trim();
  s = s.replace(/^[\[\(]+|[\]\)]+$/g, "").trim();
  s = s.replace(/^\d+\s+/, "").trim();
  return s;
}

/** Split Source-line text into document name hints (first is tried first). */
export function parseSourceHints(text) {
  if (!text) return [];
  return text
    .split(/[,;]|\s+et\s+/i)
    .map((s) => formatSourceHint(s))
    .filter(Boolean);
}

function parseInline(text, keyPrefix) {
  const nodes = [];
  const tokenRegex =
    /(\*\*[^*]+\*\*)|(!\[([^\]]*)\]\(([^)]+)\))|(\[([^\]]+)\]\(([^)]+)\))/g;
  let cursor = 0;
  let idx = 0;
  let match = tokenRegex.exec(text);

  while (match) {
    const start = match.index;
    if (start > cursor) {
      nodes.push(<span key={`${keyPrefix}-t-${idx++}`}>{text.slice(cursor, start)}</span>);
    }
    if (match[1]) {
      const token = match[1];
      nodes.push(<strong key={`${keyPrefix}-b-${idx++}`}>{token.slice(2, -2)}</strong>);
    } else if (match[2]) {
      const alt = (match[3] || "").trim();
      const src = (match[4] || "").trim();
      nodes.push(
        <span key={`${keyPrefix}-im-${idx++}`} className="msg-img-wrap msg-img-inline">
          <img
            src={resolveDocImageSrc(src)}
            alt={alt}
            className="msg-inline-img"
            loading="lazy"
          />
        </span>
      );
    } else if (match[5]) {
      const label = (match[6] || "").trim();
      const href = (match[7] || "").trim();
      if (isImagePath(href)) {
        nodes.push(
          <span key={`${keyPrefix}-iml-${idx++}`} className="msg-img-wrap msg-img-inline">
            <img
              src={resolveDocImageSrc(href)}
              alt={label}
              className="msg-inline-img"
              loading="lazy"
            />
          </span>
        );
      } else {
        const target = resolveDocHref(href);
        nodes.push(
          <a key={`${keyPrefix}-l-${idx++}`} href={target} target="_blank" rel="noreferrer">
            {label}
          </a>
        );
      }
    }
    cursor = start + match[0].length;
    match = tokenRegex.exec(text);
  }

  if (cursor < text.length) {
    nodes.push(<span key={`${keyPrefix}-end`}>{text.slice(cursor)}</span>);
  }
  return nodes;
}

function normalizeLine(line) {
  let normalized = line
    .replace(/^\s*[*•]\s{0,2}(?=[*•-])/, "- ")
    .replace(/^\s*\*\*\s*([*•-])\s*/, "$1 ")
    .replace(/\*\*(\s*[:;.,!?])/, "$1");

  const boldMarkerCount = (normalized.match(/\*\*/g) || []).length;
  if (boldMarkerCount % 2 !== 0) {
    normalized = normalized.replace(/\*\*/g, "");
  }
  return normalized;
}

const MERMAID_BLOCK_RE = /```mermaid\s*\n([\s\S]*?)```/gi;

function splitContentSegments(content) {
  const segments = [];
  let last = 0;
  let match = MERMAID_BLOCK_RE.exec(content);
  while (match) {
    if (match.index > last) {
      segments.push({ type: "text", content: content.slice(last, match.index) });
    }
    segments.push({ type: "mermaid", content: (match[1] || "").trim() });
    last = match.index + match[0].length;
    match = MERMAID_BLOCK_RE.exec(content);
  }
  MERMAID_BLOCK_RE.lastIndex = 0;
  if (last < content.length) {
    segments.push({ type: "text", content: content.slice(last) });
  }
  return segments.length ? segments : [{ type: "text", content: content || "" }];
}

function renderFormattedTextBlocks(content, options = {}, keyPrefix = "txt") {
  const { onSourceClick } = options;
  const lines = content.split(/\r?\n/).map(normalizeLine);
  const blocks = [];
  let paragraph = [];
  let listItems = [];
  let listType = null;

  const flushParagraph = () => {
    if (paragraph.length === 0) return;
    const text = paragraph.join(" ").trim();
    if (text) {
      blocks.push({ type: "p", text });
    }
    paragraph = [];
  };

  const flushList = () => {
    if (listItems.length === 0 || !listType) return;
    blocks.push({ type: listType, items: [...listItems] });
    listItems = [];
    listType = null;
  };

  lines.forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      flushList();
      return;
    }

    const imgOnly = line.match(/^!\[([^\]]*)\]\(([^)]+)\)\s*$/);
    if (imgOnly) {
      flushParagraph();
      flushList();
      blocks.push({ type: "img", alt: imgOnly[1].trim(), src: imgOnly[2].trim() });
      return;
    }

    const figOnly = line.match(/^\[Figure\s*-\s*([^\]]+)\]\(([^)]+)\)\s*$/i);
    if (figOnly && isImagePath(figOnly[2].trim())) {
      flushParagraph();
      flushList();
      blocks.push({ type: "img", alt: figOnly[1].trim(), src: figOnly[2].trim() });
      return;
    }

    const linkedImgOnly = line.match(/^\[([^\]]+)\]\(([^)]+)\)\s*$/);
    if (linkedImgOnly && isImagePath(linkedImgOnly[2].trim())) {
      flushParagraph();
      flushList();
      blocks.push({
        type: "img",
        alt: linkedImgOnly[1].trim(),
        src: linkedImgOnly[2].trim(),
      });
      return;
    }

    const sourceCandidate = line.replace(/^\*\*\s*/, "").replace(/\s*\*\*$/, "").trim();
    const sourceMatch = sourceCandidate.match(/^source\s*[:\-]\s*(.+)$/i);
    if (sourceMatch) {
      flushParagraph();
      flushList();
      blocks.push({ type: "source", text: sourceMatch[1].trim() });
      return;
    }

    const headingMatch = line.match(/^\*\*(.+)\*\*$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      blocks.push({ type: "h", text: headingMatch[1].trim() });
      return;
    }

    const bulletMatch = rawLine.match(/^(\s*)[-*•]\s+(.+)$/);
    if (bulletMatch) {
      flushParagraph();
      if (listType && listType !== "ul") {
        flushList();
      }
      listType = "ul";
      listItems.push({
        text: bulletMatch[2].trim(),
        level: Math.min(Math.floor((bulletMatch[1] || "").length / 2), 4),
      });
      return;
    }

    const orderedMatch = rawLine.match(/^(\s*)\d+[.)]\s+(.+)$/);
    if (orderedMatch) {
      flushParagraph();
      if (listType && listType !== "ol") {
        flushList();
      }
      listType = "ol";
      listItems.push({
        text: orderedMatch[2].trim(),
        level: Math.min(Math.floor((orderedMatch[1] || "").length / 2), 4),
      });
      return;
    }

    flushList();
    paragraph.push(line);
  });

  flushParagraph();
  flushList();

  return blocks.map((block, blockIndex) => {
    const blockKey = `${keyPrefix}-${blockIndex}`;
    if (block.type === "img") {
      const src = resolveDocImageSrc(block.src);
      return (
        <div key={`img-${blockKey}`} className="msg-img-wrap">
          <img
            src={src}
            alt={block.alt || ""}
            className="msg-inline-img"
            loading="lazy"
          />
        </div>
      );
    }
    if (block.type === "h") {
      return (
        <p key={`h-${blockIndex}`} className="msg-section-title">
          {parseInline(block.text, `h-${blockIndex}`)}
        </p>
      );
    }
    if (block.type === "ul") {
      return (
        <ul key={`ul-${blockIndex}`} className="msg-list">
          {block.items.map((item, itemIndex) => (
            <li
              key={`li-${blockIndex}-${itemIndex}`}
              style={{ marginInlineStart: `${item.level * 14}px` }}
            >
              {parseInline(item.text, `li-${blockIndex}-${itemIndex}`)}
            </li>
          ))}
        </ul>
      );
    }
    if (block.type === "ol") {
      return (
        <ol key={`ol-${blockIndex}`} className="msg-list msg-list-ordered">
          {block.items.map((item, itemIndex) => (
            <li
              key={`oli-${blockIndex}-${itemIndex}`}
              style={{ marginInlineStart: `${item.level * 14}px` }}
            >
              {parseInline(item.text, `oli-${blockIndex}-${itemIndex}`)}
            </li>
          ))}
        </ol>
      );
    }
    if (block.type === "source") {
      const hints = parseSourceHints(block.text);
      if (onSourceClick && hints.length) {
        return (
          <p key={`source-${blockIndex}`} className="msg-source">
            <span className="msg-source-label">Source:</span>{" "}
            {hints.map((hint, hintIndex) => (
              <Fragment key={`source-${blockIndex}-${hintIndex}`}>
                {hintIndex > 0 ? <span className="msg-source-sep">, </span> : null}
                <button
                  type="button"
                  className="msg-source-btn"
                  onClick={() => onSourceClick(hint)}
                >
                  {hint}
                </button>
              </Fragment>
            ))}
          </p>
        );
      }
      const label = parseInline(block.text, `source-${blockIndex}`);
      return (
        <p key={`source-${blockIndex}`} className="msg-source">
          <span className="msg-source-label">Source:</span> {label}
        </p>
      );
    }
    return <p key={`p-${blockKey}`}>{parseInline(block.text, `p-${blockKey}`)}</p>;
  });
}

/**
 * @param {string} content
 * @param {{ onSourceClick?: (sourceText: string) => void }} [options]
 */
export function renderFormattedMessage(content, options = {}) {
  const segments = splitContentSegments(content);
  return segments.flatMap((segment, segmentIndex) => {
    if (segment.type === "mermaid" && segment.content) {
      return [
        <Suspense key={`mmd-${segmentIndex}`} fallback={<div className="msg-mermaid-loading">Chargement du diagramme…</div>}>
          <MermaidDiagram code={segment.content} />
        </Suspense>,
      ];
    }
    if (!segment.content.trim()) return [];
    return renderFormattedTextBlocks(segment.content, options, `seg-${segmentIndex}`);
  });
}
