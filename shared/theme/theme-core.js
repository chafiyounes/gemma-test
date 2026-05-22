/**
 * SendBot theme — both theme CSS files loaded; active palette via html[data-theme].
 */

export const STORAGE_KEY = "sendbot_theme";
export const DEFAULT_THEME = "light";
export const PAGE_BG = { light: "#e8e4dc", dark: "#0f1419" };
export const THEME_LINK_TITLE = "sendbot-theme";
export const THEME_LINK_IDS = { light: "sendbot-theme-light", dark: "sendbot-theme-dark" };

export const ICONS = {
  moon:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>',
  sun:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>',
};

/** @returns {string} CSS directory prefix, e.g. "/" or "/admin-static/" */
export function getThemeCssPrefix() {
  if (typeof window !== "undefined" && window.SENDBOT_THEME_CSS_PREFIX) {
    return String(window.SENDBOT_THEME_CSS_PREFIX).replace(/\/?$/, "/");
  }
  return "/";
}

function upsertMeta(name, content) {
  let el = document.querySelector(`meta[name="${name}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute("name", name);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

/** Ensure both theme stylesheets exist and stay enabled (data-theme selects tokens). */
export function swapThemeStylesheets(theme) {
  const next = theme === "dark" ? "dark" : "light";
  const prefix = getThemeCssPrefix();
  const v = typeof window !== "undefined" && window.SENDBOT_THEME_CSS_V ? window.SENDBOT_THEME_CSS_V : "";

  (["light", "dark"]).forEach((mode) => {
    let link = document.getElementById(THEME_LINK_IDS[mode]);
    if (!link) {
      link = document.createElement("link");
      link.id = THEME_LINK_IDS[mode];
      link.rel = "stylesheet";
      link.title = THEME_LINK_TITLE;
      link.href = `${prefix}theme-${mode}.css${v}`;
      document.head.appendChild(link);
    }
    link.disabled = false;
    link.media = "all";
  });

  return next;
}

/** @param {"light"|"dark"|string} theme */
export function syncThemeToDocument(theme) {
  const next = swapThemeStylesheets(theme);
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
