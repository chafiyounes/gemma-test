/**
 * UMD build of theme-core.js for admin (loaded before admin.js).
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.sendbotSyncTheme = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : window, function () {
  var STORAGE_KEY = "sendbot_theme";
  var DEFAULT_THEME = "light";
  var PAGE_BG = { light: "#f4f6f9", dark: "#0f1419" };
  var ICONS = {
    moon:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>',
    sun:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>',
  };

  function upsertMeta(name, content) {
    var el = document.querySelector('meta[name="' + name + '"]');
    if (!el) {
      el = document.createElement("meta");
      el.setAttribute("name", name);
      document.head.appendChild(el);
    }
    el.setAttribute("content", content);
  }

  function syncThemeToDocument(theme) {
    var next = theme === "dark" ? "dark" : "light";
    var root = document.documentElement;
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

  function updateThemeToggleIcon() {
    var btn = document.getElementById("theme-toggle");
    if (!btn) return;
    var dark = document.documentElement.getAttribute("data-theme") === "dark";
    btn.setAttribute("aria-label", dark ? "Mode clair" : "Mode sombre");
    btn.setAttribute("title", dark ? "Mode clair" : "Mode sombre");
    btn.innerHTML = dark ? ICONS.sun : ICONS.moon;
  }

  function getTheme() {
    try {
      var stored = localStorage.getItem(STORAGE_KEY);
      if (stored === "dark" || stored === "light") return stored;
    } catch (e) {
      /* ignore */
    }
    return DEFAULT_THEME;
  }

  function applyTheme(theme) {
    var next = syncThemeToDocument(theme);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch (e) {
      /* ignore */
    }
    updateThemeToggleIcon();
    return next;
  }

  function toggleTheme() {
    var cur = document.documentElement.getAttribute("data-theme");
    return applyTheme(cur === "dark" ? "light" : "dark");
  }

  function initTheme() {
    applyTheme(getTheme());
  }

  return {
    STORAGE_KEY: STORAGE_KEY,
    PAGE_BG: PAGE_BG,
    syncThemeToDocument: syncThemeToDocument,
    updateThemeToggleIcon: updateThemeToggleIcon,
    getTheme: getTheme,
    applyTheme: applyTheme,
    toggleTheme: toggleTheme,
    initTheme: initTheme,
  };
});
