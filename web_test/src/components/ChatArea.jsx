import { useState, useRef, useEffect } from "react";
import { useChat } from "../context/ChatContext";
import { getClientUserId, sendChat, submitFeedback } from "../services/api";
import MessageBubble from "./MessageBubble";
import TypingIndicator from "./TypingIndicator";
import "./ChatArea.css";

const SAMPLES = [
  "Comment postuler pour un poste de livreur chez SENDIT ?",
  "Où puis-je consulter les tarifs de SENDIT ?",
  "Comment identifier les comptes vendeurs à valider ?",
  "Quels documents le vendeur doit fournir pour changer son adresse email ?",
];

export default function ChatArea({ onOpenSidebar, onLogout, session }) {
  const {
    activeConversation,
    apiHistory,
    addMessage,
    updateMessage,
    setConversationLoading,
  } = useChat();
  const [input, setInput] = useState("");
  const bottomRef = useRef(null);
  const textareaRef = useRef(null);

  const messages = activeConversation.messages;
  const loading = !!activeConversation.loading;
  const isEmpty = messages.length === 0;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height =
        Math.min(textareaRef.current.scrollHeight, 150) + "px";
    }
  }, [input]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;

    // Capture the conversation context at send time so the reply lands in
    // the originating conversation even if the user navigates away.
    const conversationId = activeConversation.id;
    const sessionId = activeConversation.sessionId;
    const historyAtSend = apiHistory;

    setInput("");
    addMessage({ role: "user", content: text }, conversationId);
    setConversationLoading(conversationId, true);

    try {
      const data = await sendChat({
        message: text,
        userId: getClientUserId(),
        sessionId,
        history: [...historyAtSend, { role: "user", content: text }],
      });
      addMessage(
        {
          role: "assistant",
          content: data.response,
          interactionId: data.interaction_id,
          feedback: null,
          metadata: data.metadata,
        },
        conversationId
      );
    } catch (err) {
      if (err.status === 401 || err.status === 403) {
        onLogout();
        return;
      }
      addMessage(
        {
          role: "assistant",
          content: `Error: ${err.message}`,
          error: true,
        },
        conversationId
      );
    } finally {
      setConversationLoading(conversationId, false);
    }
  };

  const handleFeedback = async (interactionId, feedback) => {
    const savedFeedback = await submitFeedback({
      interactionId,
      value: feedback.value,
      reason: feedback.reason,
      comment: feedback.comment,
    });
    updateMessage(
      interactionId,
      { feedback: savedFeedback },
      activeConversation.id
    );
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="chat-area">
      {/* Top bar */}
      <header className="chat-topbar">
        <button className="topbar-btn menu-btn" onClick={onOpenSidebar}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 12h18M3 6h18M3 18h18" />
          </svg>
        </button>
        <div className="topbar-badge">Acces {session?.role === "admin" ? "admin" : "client"}</div>
      </header>

      {/* Messages */}
      <div className="chat-messages">
        {isEmpty ? (
          <div className="empty-state">
            <div className="empty-icon">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
                <path d="M12 2a2 2 0 012 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 017 7h1a1 1 0 110 2h-1v1a7 7 0 01-7 7H11a7 7 0 01-7-7v-1H3a1 1 0 110-2h1a7 7 0 017-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 012-2z" />
              </svg>
            </div>
            <h2>Comment puis-je vous aider ?</h2>
            <p className="empty-subtitle">
              Posez votre question en français.
            </p>
            <div className="sample-grid">
              {SAMPLES.map((s) => (
                <button key={s} className="sample-chip" onClick={() => setInput(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="messages-list">
            {messages.map((m, i) => (
              <MessageBubble key={m.interactionId || i} message={m} onSubmitFeedback={handleFeedback} />
            ))}
            {loading && <TypingIndicator />}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Input */}
      <div className="chat-input-area">
        <div className="input-box">
          <textarea
            ref={textareaRef}
            className="chat-textarea"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Message SendBot..."
            rows={1}
            maxLength={2000}
          />
          <button
            className="send-btn"
            onClick={handleSend}
            disabled={!input.trim() || loading}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
              <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
            </svg>
          </button>
        </div>
        <span className="input-hint">
          Ce chatbot peut se tromper. Verifiez les informations importantes.
        </span>
      </div>
    </div>
  );
}
