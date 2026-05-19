const STORAGE_KEY = "sendbot_theme";
/** First visit only — never read prefers-color-scheme after that. */
const DEFAULT_THEME = "light";

const PAGE_BG = { light: "#f4f6f9", dark: "#0f1419" };

function upsertMeta(name, content) {
  let el = document.querySelector(`meta[name="${name}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute("name", name);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

/** Lock html + meta tags so Chromium/Brave do not apply OS “forced” colors. */
export function syncThemeToDocument(theme) {
  const next = theme === "dark" ? "dark" : "light";
  const root = document.documentElement;
  root.setAttribute("data-theme", next);
  root.style.colorScheme = next;
  root.style.backgroundColor = PAGE_BG[next];
  upsertMeta("color-scheme", next);
  upsertMeta("theme-color", PAGE_BG[next]);
  if (document.body) {
    document.body.style.backgroundColor = PAGE_BG[next];
    document.body.style.colorScheme = next;
  }
  return next;
}

export function getTheme() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "dark" || stored === "light") return stored;
  } catch {
    /* ignore */
  }
  return DEFAULT_THEME;
}

export function applyTheme(theme) {
  const next = syncThemeToDocument(theme);
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {
    /* ignore */
  }
  return next;
}

export function toggleTheme() {
  return applyTheme(getTheme() === "dark" ? "light" : "dark");
}

/** Call before React paint (also in index.html inline script). */
export function initTheme() {
  applyTheme(getTheme());
}
