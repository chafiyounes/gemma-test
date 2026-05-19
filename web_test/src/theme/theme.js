const STORAGE_KEY = "sendbot_theme";
/** First visit only — never read prefers-color-scheme after that. */
const DEFAULT_THEME = "light";

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
  const next = theme === "dark" ? "dark" : "light";
  const root = document.documentElement;
  root.setAttribute("data-theme", next);
  // Lock native UI (scrollbars, inputs) to app theme — ignore OS color scheme.
  root.style.colorScheme = next;
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
