const TIMEOUT_MS = 120_000;
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

export function setApiUrl(url) {
  localStorage.setItem(API_URL_STORAGE_KEY, url.replace(/\/+$/, ""));
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

export async function login(password) {
  const res = await apiFetch("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
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

export async function checkHealth() {
  const res = await fetch(buildUrl("/health"), {
    credentials: "include",
    signal: AbortSignal.timeout(10_000),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function sendChat({ message, userId, sessionId, history, category }) {
  const res = await apiFetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      user_id: userId || "anonymous",
      session_id: sessionId,
      conversation_history: history.slice(-20),
      category: category || null,
      debug_rag: true,
    }),
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  return res.json();
}

export async function fetchCategories() {
  const res = await apiFetch("/categories", {
    signal: AbortSignal.timeout(10_000),
  });
  return res.json();
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
  return res.json();
}
