/**
 * UMD build of theme-core.js for admin (keep in sync).
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
  var THEME_LINK_TITLE = "sendbot-theme";
  var THEME_LINK_IDS = { light: "sendbot-theme-light", dark: "sendbot-theme-dark" };
  var ICONS = {
    moon:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>',
    sun:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>',
  };

  function getThemeCssPrefix() {
    if (root.SENDBOT_THEME_CSS_PREFIX) {
      return String(root.SENDBOT_THEME_CSS_PREFIX).replace(/\/?$/, "/");
    }
    return "/";
  }

  function upsertMeta(name, content) {
    var el = document.querySelector('meta[name="' + name + '"]');
    if (!el) {
      el = document.createElement("meta");
      el.setAttribute("name", name);
      document.head.appendChild(el);
    }
    el.setAttribute("content", content);
  }

  function swapThemeStylesheets(theme) {
    var next = theme === "dark" ? "dark" : "light";
    var prefix = getThemeCssPrefix();
    var v = root.SENDBOT_THEME_CSS_V || "";
    ["light", "dark"].forEach(function (mode) {
      var link = document.getElementById(THEME_LINK_IDS[mode]);
      if (!link) {
        link = document.createElement("link");
        link.id = THEME_LINK_IDS[mode];
        link.rel = "stylesheet";
        link.title = THEME_LINK_TITLE;
        link.href = prefix + "theme-" + mode + ".css" + v;
        document.head.appendChild(link);
      }
      link.disabled = mode !== next;
      link.media = "all";
    });
    return next;
  }

  function syncThemeToDocument(theme) {
    var next = swapThemeStylesheets(theme);
    var html = document.documentElement;
    html.setAttribute("data-theme", next);
    html.style.colorScheme = next;
    html.style.backgroundColor = PAGE_BG[next];
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
    swapThemeStylesheets: swapThemeStylesheets,
    syncThemeToDocument: syncThemeToDocument,
    updateThemeToggleIcon: updateThemeToggleIcon,
    getTheme: getTheme,
    applyTheme: applyTheme,
    toggleTheme: toggleTheme,
    initTheme: initTheme,
  };
});
