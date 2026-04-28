import { createContext, useContext, useReducer, useCallback } from "react";
import { v4 as uuid } from "uuid";

const ChatContext = createContext();

const newConversation = () => ({
  id: uuid(),
  title: "New chat",
  messages: [],
  sessionId: uuid(),
  createdAt: Date.now(),
  loading: false,
});

const initialState = () => {
  const saved = localStorage.getItem("sendbot_state");
  if (saved) {
    try {
      const parsed = JSON.parse(saved);
      if (parsed.conversations?.length) {
        // Defensive: any stale `loading=true` from a previous session must be
        // cleared so the typing indicator does not show on page reload.
        parsed.conversations = parsed.conversations.map((c) => ({
          ...c,
          loading: false,
        }));
        return parsed;
      }
    } catch {}
  }
  const conv = newConversation();
  return { conversations: [conv], activeId: conv.id };
};

function reducer(state, action) {
  let next;
  switch (action.type) {
    case "NEW_CHAT": {
      const conv = newConversation();
      next = {
        ...state,
        conversations: [conv, ...state.conversations],
        activeId: conv.id,
      };
      break;
    }
    case "SELECT_CHAT":
      next = { ...state, activeId: action.id };
      break;
    case "DELETE_CHAT": {
      const filtered = state.conversations.filter((c) => c.id !== action.id);
      if (!filtered.length) {
        const conv = newConversation();
        next = { conversations: [conv], activeId: conv.id };
      } else {
        next = {
          ...state,
          conversations: filtered,
          activeId:
            state.activeId === action.id ? filtered[0].id : state.activeId,
        };
      }
      break;
    }
    case "ADD_MESSAGE": {
      // Always target the conversation passed in `action.conversationId` so
      // that an in-flight reply lands in the conversation it was sent from,
      // not whichever conversation the user happens to be viewing now.
      const targetId = action.conversationId || state.activeId;
      next = {
        ...state,
        conversations: state.conversations.map((c) => {
          if (c.id !== targetId) return c;
          const msgs = [...c.messages, action.message];
          const title =
            c.messages.length === 0 && action.message.role === "user"
              ? action.message.content.slice(0, 40) +
                (action.message.content.length > 40 ? "..." : "")
              : c.title;
          return { ...c, messages: msgs, title };
        }),
      };
      break;
    }
    case "UPDATE_LAST_BOT": {
      const targetId = action.conversationId || state.activeId;
      next = {
        ...state,
        conversations: state.conversations.map((c) => {
          if (c.id !== targetId) return c;
          const msgs = [...c.messages];
          const last = msgs[msgs.length - 1];
          if (last?.role === "assistant") {
            msgs[msgs.length - 1] = { ...last, ...action.updates };
          }
          return { ...c, messages: msgs };
        }),
      };
      break;
    }
    case "UPDATE_MESSAGE": {
      const targetId = action.conversationId || state.activeId;
      next = {
        ...state,
        conversations: state.conversations.map((c) => {
          if (c.id !== targetId) return c;
          return {
            ...c,
            messages: c.messages.map((message) => {
              if (message.interactionId !== action.interactionId) {
                return message;
              }
              return { ...message, ...action.updates };
            }),
          };
        }),
      };
      break;
    }
    case "SET_LOADING": {
      const targetId = action.conversationId || state.activeId;
      next = {
        ...state,
        conversations: state.conversations.map((c) =>
          c.id === targetId ? { ...c, loading: !!action.loading } : c
        ),
      };
      break;
    }
    case "CLEAR_ALL": {
      const conv = newConversation();
      next = { conversations: [conv], activeId: conv.id };
      break;
    }
    default:
      return state;
  }
  localStorage.setItem("sendbot_state", JSON.stringify(next));
  return next;
}

export function ChatProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, null, initialState);

  const activeConversation =
    state.conversations.find((c) => c.id === state.activeId) ||
    state.conversations[0];

  const apiHistory = activeConversation.messages
    .filter((m) => m.role === "user" || m.role === "assistant")
    .map((m) => ({ role: m.role, content: m.content }));

  const value = {
    conversations: state.conversations,
    activeConversation,
    activeId: state.activeId,
    apiHistory,
    dispatch,
    newChat: useCallback(() => dispatch({ type: "NEW_CHAT" }), []),
    selectChat: useCallback((id) => dispatch({ type: "SELECT_CHAT", id }), []),
    deleteChat: useCallback((id) => dispatch({ type: "DELETE_CHAT", id }), []),
    addMessage: useCallback(
      (message, conversationId) =>
        dispatch({ type: "ADD_MESSAGE", message, conversationId }),
      []
    ),
    updateLastBot: useCallback(
      (updates, conversationId) =>
        dispatch({ type: "UPDATE_LAST_BOT", updates, conversationId }),
      []
    ),
    updateMessage: useCallback(
      (interactionId, updates, conversationId) =>
        dispatch({
          type: "UPDATE_MESSAGE",
          interactionId,
          updates,
          conversationId,
        }),
      []
    ),
    setConversationLoading: useCallback(
      (conversationId, loading) =>
        dispatch({ type: "SET_LOADING", conversationId, loading }),
      []
    ),
    clearAll: useCallback(() => dispatch({ type: "CLEAR_ALL" }), []),
  };

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export const useChat = () => useContext(ChatContext);
