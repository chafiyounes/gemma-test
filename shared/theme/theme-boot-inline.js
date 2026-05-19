/* Copy into index.html <script> — keep in sync with web_test/src/theme/theme.js */
(function () {
  var PAGE_BG = { light: "#f4f6f9", dark: "#0f1419" };
  var theme = "light";
  try {
    var t = localStorage.getItem("sendbot_theme");
    if (t === "dark" || t === "light") theme = t;
  } catch (e) { /* ignore */ }
  var html = document.documentElement;
  html.setAttribute("data-theme", theme);
  html.style.colorScheme = theme;
  html.style.backgroundColor = PAGE_BG[theme];
  function meta(name, content) {
    var el = document.querySelector('meta[name="' + name + '"]');
    if (!el) {
      el = document.createElement("meta");
      el.setAttribute("name", name);
      document.head.appendChild(el);
    }
    el.setAttribute("content", content);
  }
  meta("color-scheme", theme);
  meta("theme-color", PAGE_BG[theme]);
})();
