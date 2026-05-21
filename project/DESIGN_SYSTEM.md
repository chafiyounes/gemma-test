# SendBot design system

Shared visual language for **web_test** (chat) and **admin_site** (console).

**Tokens:** [`../shared/theme/theme-tokens.css`](../shared/theme/theme-tokens.css)  
**Theme key:** `localStorage.sendbot_theme` → `light` | `dark` (default **light**)

**Code:** [`shared/theme/theme-core.js`](../shared/theme/theme-core.js) (chat ESM) and [`shared/theme/theme-sync.js`](../shared/theme/theme-sync.js) (admin UMD copy — keep in sync).

**OS / browser:** Theme does **not** follow `prefers-color-scheme`. Only `data-theme` on `<html>`, `color-scheme` / `theme-color` meta tags, and the toggle control appearance. First visit uses the **light** preset until the user switches (stored in `localStorage`).

**Brave:** If the page still follows Brave’s global colors, disable **Settings → Appearance → “Use Brave colors for all websites”** (or add a Shields exception for this site). Brave can apply a compositor-level recolor that no site CSS can fully override.

---

## Principles

1. **Neutrals first** — page and panels use slate greys; SENDIT orange is accent only (~10–15% of visible UI).
2. **No heavy orange glow** — avoid large radial gradients; use flat or very subtle backgrounds.
3. **Consistent chrome** — same borders, radii, and button styles in chat and admin.
4. **Document preview** — Word tab always uses paper white (`--doc-paper-*`); modal chrome follows theme.

---

## Palette (summary)

| Token | Light | Dark |
|-------|-------|------|
| `--bg-page` | `#f4f6f9` | `#0f1419` |
| `--bg-surface` | `#ffffff` | `#1a2332` |
| `--accent` | `#d97745` | `#e8956a` |
| `--secondary` | `#2b9bab` | `#3db4c4` |

---

## Theme toggle

- **Light mode:** moon icon → switches to dark.
- **Dark mode:** sun icon → switches to light.
- Placed in chat top bar and admin sidebar; also on login screen.

---

## Maintenance

When changing colors, edit **only** `shared/theme/theme-tokens.css`, then copy to `admin_site/assets/theme-tokens.css` (or keep files in sync). Chat imports tokens via `web_test/src/index.css`.
