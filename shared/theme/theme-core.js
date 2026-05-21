/**
 * SendBot theme — single source for chat (ESM) and admin (UMD via theme-sync.js).
 * Theme is ONLY data-theme + localStorage; never prefers-color-scheme.
 */

export const STORAGE_KEY = "sendbot_theme";
export const DEFAULT_THEME = "light";
export const PAGE_BG = { light: "#f4f6f9", dark: "#0f1419" };

export const ICONS = {
  moon:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>',
  sun:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>',
};

function upsertMeta(name, content) {
  let el = document.querySelector(`meta[name="${name}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute("name", name);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

/** @param {"light"|"dark"|string} theme */
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

/** Sync moon/sun icon with current theme (light → moon, dark → sun). */
export function updateThemeToggleIcon() {
  const btn = document.getElementById("theme-toggle");
  if (!btn) return;
  const dark = document.documentElement.getAttribute("data-theme") === "dark";
  btn.setAttribute("aria-label", dark ? "Mode clair" : "Mode sombre");
  btn.setAttribute("title", dark ? "Mode clair" : "Mode sombre");
  btn.innerHTML = dark ? ICONS.sun : ICONS.moon;
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

/** @param {"light"|"dark"|string} theme */
export function applyTheme(theme) {
  const next = syncThemeToDocument(theme);
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {
    /* ignore */
  }
  updateThemeToggleIcon();
  return next;
}

export function toggleTheme() {
  const cur = document.documentElement.getAttribute("data-theme");
  return applyTheme(cur === "dark" ? "light" : "dark");
}

export function initTheme() {
  applyTheme(getTheme());
}
