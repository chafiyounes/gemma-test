import { createContext, useContext, useReducer, useCallback, useEffect } from "react";
import { v4 as uuid } from "uuid";
import { fetchChatThreads, fetchThreadMessages, hideAllThreads, hideThread } from "../services/api";

const ChatContext = createContext();

const newConversation = () => {
  const id = uuid();
  return {
    id,
    title: "New chat",
    messages: [],
    sessionId: id,
    createdAt: Date.now(),
    loading: false,
    needsFetch: false,
  };
};

const initialState = () => {
  const conv = newConversation();
  return { conversations: [conv], activeId: conv.id };
};

function reducer(state, action) {
  let next;
  switch (action.type) {
    case "REPLACE_STATE": {
      next = action.state;
      break;
    }
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
    case "SET_MESSAGES": {
      const targetId = action.conversationId || state.activeId;
      next = {
        ...state,
        conversations: state.conversations.map((c) => {
          if (c.id !== targetId) return c;
          return {
            ...c,
            messages: action.messages,
            needsFetch: false,
          };
        }),
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
  try {
    localStorage.setItem("sendbot_state", JSON.stringify(next));
  } catch {
    /* ignore quota */
  }
  return next;
}

export function ChatProvider({ children, session }) {
  const [state, dispatch] = useReducer(reducer, null, initialState);

  const activeConversation =
    state.conversations.find((c) => c.id === state.activeId) ||
    state.conversations[0];

  const apiHistory = activeConversation.messages
    .filter((m) => m.role === "user" || m.role === "assistant")
    .map((m) => ({ role: m.role, content: m.content }));

  useEffect(() => {
    if (!session?.authenticated || !session?.user_id) return;
    let cancelled = false;
    (async () => {
      try {
        const { threads } = await fetchChatThreads();
        if (cancelled) return;
        if (!threads?.length) {
          dispatch({ type: "REPLACE_STATE", state: initialState() });
          return;
        }
        const convs = threads.map((t) => ({
          id: t.id,
          sessionId: t.id,
          title: t.title || "Chat",
          messages: [],
          loading: false,
          createdAt: Date.parse(t.updated_at) || Date.now(),
          needsFetch: true,
        }));
        dispatch({
          type: "REPLACE_STATE",
          state: { conversations: convs, activeId: convs[0].id },
        });
      } catch {
        /* keep local state */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [session?.authenticated, session?.user_id]);

  useEffect(() => {
    if (!session?.authenticated || !activeConversation?.sessionId) return;
    if (!activeConversation.needsFetch) return;
    if (activeConversation.messages.length > 0) return;
    let cancelled = false;
    (async () => {
      try {
        const { messages } = await fetchThreadMessages(activeConversation.sessionId);
        if (cancelled) return;
        dispatch({
          type: "SET_MESSAGES",
          conversationId: activeConversation.id,
          messages: messages || [],
        });
      } catch {
        dispatch({
          type: "SET_MESSAGES",
          conversationId: activeConversation.id,
          messages: [],
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [
    session?.authenticated,
    activeConversation?.id,
    activeConversation?.sessionId,
    activeConversation?.needsFetch,
    activeConversation?.messages.length,
  ]);

  const value = {
    conversations: state.conversations,
    activeConversation,
    activeId: state.activeId,
    apiHistory,
    dispatch,
    session,
    newChat: useCallback(() => dispatch({ type: "NEW_CHAT" }), []),
    selectChat: useCallback((id) => dispatch({ type: "SELECT_CHAT", id }), []),
    deleteChat: useCallback((id) => dispatch({ type: "DELETE_CHAT", id }), []),
    removeChat: useCallback(async (conv) => {
      if (session?.authenticated && conv?.sessionId) {
        try {
          await hideThread(conv.sessionId);
        } catch {
          /* still drop from UI */
        }
      }
      dispatch({ type: "DELETE_CHAT", id: conv.id });
    }, [session?.authenticated]),
    clearAllChats: useCallback(async () => {
      if (session?.authenticated && session?.user_id) {
        try {
          await hideAllThreads();
        } catch {
          /* ignore */
        }
      }
      dispatch({ type: "CLEAR_ALL" });
    }, [session?.authenticated, session?.user_id]),
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
  };

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export const useChat = () => useContext(ChatContext);
