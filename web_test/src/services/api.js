// Long RAG context + up to ~2k completion tokens can exceed 2 minutes on busy GPUs.
const TIMEOUT_MS = 240_000;
const API_URL_STORAGE_KEY = "sendbot_api_url";
const USER_ID_STORAGE_KEY = "sendbot_user_id";
const DEFAULT_API_URL = (import.meta.env.VITE_API_URL || "").replace(/\/+$/, "");

function buildUrl(path) {
  const base = getApiUrl();
  return `${base}${path}`;
}

async function apiFetch(path, options = {}) {
  const response = await fetch(buildUrl(path), {
    credentials: "include",
    ...options,
  });

  if (!response.ok) {
    const errorPayload = await response.json().catch(() => ({}));
    const error = new Error(errorPayload.detail || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }

  return response;
}

export function getApiUrl() {
  return localStorage.getItem(API_URL_STORAGE_KEY) || DEFAULT_API_URL;
}

/** Display labels for API auth roles (administrator | manager | user). */
export function sessionRoleLabel(role) {
  const r = String(role || "").toLowerCase();
  if (r === "administrator" || r === "admin") return "Administrateur";
  if (r === "manager") return "Gestionnaire";
  return "Utilisateur";
}

export function isPrivilegedChatRole(role) {
  const r = String(role || "").toLowerCase();
  return r === "administrator" || r === "admin" || r === "manager";
}

export function getClientUserId() {
  const existing = localStorage.getItem(USER_ID_STORAGE_KEY);
  if (existing) {
    return existing;
  }

  const generated = `web-${crypto.randomUUID()}`;
  localStorage.setItem(USER_ID_STORAGE_KEY, generated);
  return generated;
}

export async function getSession() {
  const res = await apiFetch("/auth/session", {
    signal: AbortSignal.timeout(10_000),
  });
  return res.json();
}

export async function login({ username, password }) {
  const res = await apiFetch("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
    signal: AbortSignal.timeout(15_000),
  });
  return res.json();
}

export async function logout() {
  await fetch(buildUrl("/auth/logout"), {
    method: "POST",
    credentials: "include",
    signal: AbortSignal.timeout(10_000),
  });
}

export async function sendChat({ message, sessionId, history, category }) {
  const payload = {
    message,
    session_id: sessionId,
    conversation_history: history.slice(-20),
  };
  if (category != null && category !== "") {
    payload.category = category;
  }
  if (import.meta.env.VITE_AGENTIC_RAG === "true") {
    payload.agentic_rag = true;
  }
  const res = await apiFetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  return res.json();
}

export async function fetchChatThreads() {
  const res = await apiFetch("/chat/threads", { signal: AbortSignal.timeout(20_000) });
  return res.json();
}

export async function fetchThreadMessages(threadId) {
  const res = await apiFetch(`/chat/threads/${encodeURIComponent(threadId)}/messages`, {
    signal: AbortSignal.timeout(60_000),
  });
  return res.json();
}

export async function hideThread(threadId) {
  await apiFetch(`/chat/threads/${encodeURIComponent(threadId)}/hide`, {
    method: "POST",
    signal: AbortSignal.timeout(15_000),
  });
}

export async function hideAllThreads() {
  await apiFetch("/chat/threads/hide-all", {
    method: "POST",
    signal: AbortSignal.timeout(20_000),
  });
}

export async function submitFeedback({ interactionId, value, reason, comment }) {
  const res = await apiFetch("/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      interaction_id: interactionId,
      value,
      reason,
      comment,
    }),
    signal: AbortSignal.timeout(20_000),
  });
  // The /feedback endpoint returns 204 No Content — do not parse JSON
  return { value, reason, comment };
}

/** @returns {{ categories: { name: string, doc_count: number, doc_names: string[] }[] }} */
export async function fetchDocumentCategories() {
  const res = await apiFetch("/categories", { signal: AbortSignal.timeout(15_000) });
  return res.json();
}

/** @returns {Promise<{ resolved_stem: string, resolved_category: string, title: string, has_docx: boolean, has_md: boolean, markdown: string, docx_url?: string }>} */
export async function fetchDocumentPreview({ name, category }) {
  const params = new URLSearchParams({ name });
  if (category) params.set("category", category);
  const res = await apiFetch(`/api/documents/preview?${params.toString()}`, {
    signal: AbortSignal.timeout(60_000),
  });
  return res.json();
}

export async function fetchDocumentFileBlob(urlPath) {
  const response = await fetch(buildUrl(urlPath), {
    credentials: "include",
    signal: AbortSignal.timeout(120_000),
  });
  if (!response.ok) {
    const errorPayload = await response.json().catch(() => ({}));
    const error = new Error(errorPayload.detail || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.blob();
}
