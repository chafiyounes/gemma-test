/**
 * Apply SendBot theme to the document (chat + admin).
 * Plain JS — safe to inline in HTML or import as ESM from web_test.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.sendbotSyncTheme = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : window, function () {
  var PAGE_BG = { light: "#f4f6f9", dark: "#0f1419" };

  function upsertMeta(name, content) {
    var el = document.querySelector('meta[name="' + name + '"]');
    if (!el) {
      el = document.createElement("meta");
      el.setAttribute("name", name);
      document.head.appendChild(el);
    }
    el.setAttribute("content", content);
  }

  /**
   * @param {"light"|"dark"} theme
   * @returns {"light"|"dark"}
   */
  function syncThemeToDocument(theme) {
    var next = theme === "dark" ? "dark" : "light";
    var html = document.documentElement;
    html.setAttribute("data-theme", next);
    html.style.colorScheme = next;
    html.style.backgroundColor = PAGE_BG[next];

    // Chromium / Brave: declare a single scheme (not "light dark") to reduce auto-recolor.
    upsertMeta("color-scheme", next);
    upsertMeta("theme-color", PAGE_BG[next]);
  }

  return { syncThemeToDocument: syncThemeToDocument, PAGE_BG: PAGE_BG };
});
