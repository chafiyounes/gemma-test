import { useState } from "react";
import "./MessageBubble.css";

const DISLIKE_REASONS = ["Hors sujet", "Incomplete", "Incorrecte"];

// Detect the dominant script of a message so we can force the correct
// paragraph direction. `dir="auto"` only inspects the first strong character,
// which mis-renders Arabic paragraphs that happen to start with a Latin token
// (e.g. "SENDIT كتقدم..." was being laid out LTR, scrambling the Arabic).
function detectDir(text) {
  if (!text) return "ltr";
  const arabic = (text.match(/[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/g) || []).length;
  const latin = (text.match(/[A-Za-z\u00C0-\u024F]/g) || []).length;
  return arabic >= latin ? "rtl" : "ltr";
}

function parseInline(text, keyPrefix) {
  const nodes = [];
  const tokenRegex = /(\*\*[^*]+\*\*|\[[^\]]+\]\((https?:\/\/[^\s)]+)\))/g;
  let cursor = 0;
  let idx = 0;
  let match = tokenRegex.exec(text);

  while (match) {
    const [token] = match;
    const start = match.index;
    if (start > cursor) {
      nodes.push(<span key={`${keyPrefix}-t-${idx++}`}>{text.slice(cursor, start)}</span>);
    }
    if (token.startsWith("**") && token.endsWith("**")) {
      nodes.push(<strong key={`${keyPrefix}-b-${idx++}`}>{token.slice(2, -2)}</strong>);
    } else {
      const linkMatch = token.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/);
      if (linkMatch) {
        nodes.push(
          <a key={`${keyPrefix}-l-${idx++}`} href={linkMatch[2]} target="_blank" rel="noreferrer">
            {linkMatch[1]}
          </a>
        );
      } else {
        nodes.push(<span key={`${keyPrefix}-f-${idx++}`}>{token}</span>);
      }
    }
    cursor = start + token.length;
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
    // Broken markdown from model output: keep text, drop dangling markers.
    normalized = normalized.replace(/\*\*/g, "");
  }
  return normalized;
}

function renderFormattedMessage(content) {
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

    const headingMatch = line.match(/^\*\*(.+)\*\*$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      blocks.push({ type: "h", text: headingMatch[1].trim() });
      return;
    }

    const sourceMatch = line.match(/^\**\s*source\s*[:\-]\s*(.+)\s*\**$/i);
    if (sourceMatch) {
      flushParagraph();
      flushList();
      blocks.push({ type: "source", text: sourceMatch[1].trim() });
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
      return (
        <p key={`source-${blockIndex}`} className="msg-source">
          <span className="msg-source-label">Source:</span>{" "}
          {parseInline(block.text, `source-${blockIndex}`)}
        </p>
      );
    }
    return <p key={`p-${blockIndex}`}>{parseInline(block.text, `p-${blockIndex}`)}</p>;
  });
}

export default function MessageBubble({ message, onSubmitFeedback }) {
  const isUser = message.role === "user";
  const isError = message.error;
  const textDir = detectDir(message.content);
  const [composerOpen, setComposerOpen] = useState(false);
  const [reason, setReason] = useState(DISLIKE_REASONS[0]);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const feedbackValue = message.feedback?.value;

  const handleLike = async () => {
    if (!message.interactionId || busy || feedbackValue === "like") {
      return;
    }
    setBusy(true);
    setError("");
    try {
      await onSubmitFeedback(message.interactionId, { value: "like" });
    } catch (submissionError) {
      setError(submissionError.message || "Impossible d'enregistrer le feedback.");
    } finally {
      setBusy(false);
    }
  };

  const handleDislike = async () => {
    if (!message.interactionId || busy) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      await onSubmitFeedback(message.interactionId, {
        value: "dislike",
        reason,
        comment: comment.trim() || undefined,
      });
      setComposerOpen(false);
    } catch (submissionError) {
      setError(submissionError.message || "Impossible d'enregistrer le feedback.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`msg-row ${isUser ? "user" : "bot"}`}>
      {!isUser && (
        <div className="msg-avatar bot-avatar">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2a2 2 0 012 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 017 7h1a1 1 0 110 2h-1v1a7 7 0 01-7 7H11a7 7 0 01-7-7v-1H3a1 1 0 110-2h1a7 7 0 017-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 012-2zm-1 9a2 2 0 100 4 2 2 0 000-4zm4 0a2 2 0 100 4 2 2 0 000-4z" />
          </svg>
        </div>
      )}
      <div className={`msg-bubble ${isUser ? "user-bubble" : "bot-bubble"} ${isError ? "error-bubble" : ""}`}>
        <div className="msg-text" dir={textDir}>
          {isUser || isError ? message.content : renderFormattedMessage(message.content)}
        </div>
        {!isUser && !isError && message.interactionId ? (
          <div className="feedback-section">
            <div className="feedback-actions">
              <button
                className={`feedback-btn ${feedbackValue === "like" ? "active" : ""}`}
                type="button"
                onClick={handleLike}
                disabled={busy}
              >
                Utile
              </button>
              <button
                className={`feedback-btn ${feedbackValue === "dislike" ? "active" : ""}`}
                type="button"
                onClick={() => setComposerOpen((open) => !open)}
                disabled={busy}
              >
                A revoir
              </button>
              {message.feedback ? (
                <span className="feedback-status">
                  {message.feedback.value === "like"
                    ? "Feedback enregistre"
                    : `Retour enregistre${message.feedback.reason ? `: ${message.feedback.reason}` : ""}`}
                </span>
              ) : null}
            </div>

            {composerOpen ? (
              <div className="feedback-composer">
                <label className="feedback-label">Pourquoi cette reponse ne convient pas ?</label>
                <div className="feedback-reasons">
                  {DISLIKE_REASONS.map((option) => (
                    <button
                      key={option}
                      type="button"
                      className={`feedback-reason ${reason === option ? "selected" : ""}`}
                      onClick={() => setReason(option)}
                    >
                      {option}
                    </button>
                  ))}
                </div>
                <textarea
                  className="feedback-comment"
                  value={comment}
                  onChange={(event) => setComment(event.target.value)}
                  placeholder="Ajouter un commentaire (optionnel)"
                  maxLength={1000}
                  rows={3}
                />
                <div className="feedback-composer-actions">
                  <button type="button" className="feedback-secondary" onClick={() => setComposerOpen(false)}>
                    Annuler
                  </button>
                  <button type="button" className="feedback-primary" onClick={handleDislike} disabled={busy}>
                    {busy ? "Enregistrement..." : "Envoyer"}
                  </button>
                </div>
              </div>
            ) : null}

            {error ? <div className="feedback-error">{error}</div> : null}
          </div>
        ) : null}
      </div>
      {isUser && (
        <div className="msg-avatar user-avatar">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 12c2.7 0 5-2.3 5-5s-2.3-5-5-5-5 2.3-5 5 2.3 5 5 5zm0 2c-3.3 0-10 1.7-10 5v3h20v-3c0-3.3-6.7-5-10-5z" />
          </svg>
        </div>
      )}
    </div>
  );
}
