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
        <div className="msg-text" dir={textDir}>{message.content}</div>
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
