# SendBot design system

Shared visual language for **web_test** (chat) and **admin_site** (console).

**Status (May 2026):** Chat and admin share the same light/dark tokens. Admin `admin.css` uses theme variables (no hardcoded light-on-dark borders/pills). Hard-refresh after deploy if styles look stale.

---

## Theme storage

| Item | Value |
|------|--------|
| Key | `localStorage.sendbot_theme` → `light` \| `dark` |
| Default | **light** |
| HTML attribute | `data-theme` on `<html>` |
| Toggle | Moon in light (→ dark), sun in dark (→ light) |

Theme does **not** follow `prefers-color-scheme`. OS/browser must not drive the active preset after first visit (only the in-app toggle + stored value).

---

## File layout (source of truth)

| File | Role |
|------|------|
| [`shared/theme/theme-light.css`](../shared/theme/theme-light.css) | Full light palette on `html` + `.sendbot-theme-island` |
| [`shared/theme/theme-dark.css`](../shared/theme/theme-dark.css) | Full dark palette |
| [`shared/theme/theme-base.css`](../shared/theme/theme-base.css) | Toggle, panel harmonization, `.sendbot-theme-island` wrapper |
| [`shared/theme/theme-core.js`](../shared/theme/theme-core.js) | Chat (ESM): apply, toggle, file-swap |
| [`shared/theme/theme-sync.js`](../shared/theme/theme-sync.js) | Admin (UMD) — **keep in sync** with `theme-core.js` |
| [`shared/theme/theme-tokens.css`](../shared/theme/theme-tokens.css) | Legacy shim → imports `theme-base.css` only |

**Chat:** Vite imports `theme-base` via `web_test/src/index.css`; `theme-light.css` / `theme-dark.css` served from `web_test/public/` with static `<link title="sendbot-theme">` in `index.html`.

**Admin:** Copy `theme-*.css` + `theme-sync.js` to `admin_site/assets/`. `index.html` must load **`theme-light.css` / `theme-dark.css` before `theme-base.css` and `admin.css`** so `var(--*)` resolves.

---

## File-swap pattern

Two physical stylesheets; exactly one enabled via `<link disabled>`:

```html
<link id="sendbot-theme-light" title="sendbot-theme" href=".../theme-light.css" />
<link id="sendbot-theme-dark" title="sendbot-theme" href=".../theme-dark.css" disabled />
```

`applyTheme()` / `swapThemeStylesheets()` flips `disabled` and updates meta `color-scheme` / `theme-color`.

**Do not** use `contain: style` on `.sendbot-theme-island` — it breaks CSS variable inheritance into admin/chat layout.

---

## Palette (summary)

| Token | Light | Dark |
|-------|-------|------|
| `--bg-page` | `#f4f6f9` | `#0f1419` |
| `--bg-surface` | `#ffffff` | `#1a2332` |
| `--accent` | `#d97745` | `#e8956a` |
| `--secondary` | `#2b9bab` | `#3db4c4` |

Accent ~10–15% of visible UI; neutrals carry surfaces.

---

## Document preview

Word tab always uses paper white (`--doc-paper-*`). Modal chrome follows active theme. See [`DOCUMENT_PREVIEW.md`](DOCUMENT_PREVIEW.md).

---

## Brave / forced colors

If the page still looks tinted wrong: **Settings → Appearance → disable “Use Brave colors for all websites”**. No site CSS can fully override Brave’s compositor recolor.

---

## Maintenance

1. Edit palettes in `shared/theme/theme-light.css` and `theme-dark.css`.
2. Copy to `admin_site/assets/` and `web_test/public/`.
3. Bump `?v=` query strings in `admin_site/index.html` and `web_test/index.html` after deploy.
4. `cd web_test && npm run build` when chat CSS/JS changes.

---

## Known issues (admin)

- Brave “Use Brave colors for all websites” can still override site theme — disable in browser settings.
- Bump `?v=` in `admin_site/index.html` after CSS deploy if CDN/browser cache persists.

Track progress in [`ROADMAP.md`](ROADMAP.md) §3.
