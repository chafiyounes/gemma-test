import { useState } from "react";
import { useChat } from "../context/ChatContext";
import "./Sidebar.css";

export default function Sidebar({ isOpen, onClose, session, onLogout }) {
  const { conversations, activeId, newChat, selectChat, deleteChat, clearAll } =
    useChat();
  const [hoveredId, setHoveredId] = useState(null);

  return (
    <>
      <div className={`sidebar-overlay ${isOpen ? "open" : ""}`} onClick={onClose} />
      <aside className={`sidebar ${isOpen ? "open" : ""}`}>
        <div className="sidebar-header">
          <span className="sidebar-brand">SendBot</span>
          <button className="new-chat-btn" onClick={() => { newChat(); onClose(); }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 5v14M5 12h14" />
            </svg>
            New chat
          </button>
        </div>

        <nav className="sidebar-conversations">
          {conversations.map((conv) => (
            <div
              key={conv.id}
              className={`conv-item ${conv.id === activeId ? "active" : ""}`}
              onClick={() => { selectChat(conv.id); onClose(); }}
              onMouseEnter={() => setHoveredId(conv.id)}
              onMouseLeave={() => setHoveredId(null)}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
              </svg>
              <span className="conv-title">{conv.title}</span>
              {hoveredId === conv.id && conversations.length > 1 && (
                <button
                  className="conv-delete"
                  onClick={(e) => { e.stopPropagation(); deleteChat(conv.id); }}
                  title="Delete"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6h14" />
                  </svg>
                </button>
              )}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-session-card">
            <div className="sidebar-session-label">Session active</div>
            <div className="sidebar-session-role">
              {session?.role === "admin" ? "Administrateur" : "Utilisateur"}
            </div>
          </div>
          <button className="sidebar-footer-btn" onClick={clearAll}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6h14" />
            </svg>
            Clear all chats
          </button>
          <button className="sidebar-footer-btn logout" onClick={onLogout}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" />
              <path d="M16 17l5-5-5-5" />
              <path d="M21 12H9" />
            </svg>
            Se deconnecter
          </button>
        </div>
      </aside>
    </>
  );
}
