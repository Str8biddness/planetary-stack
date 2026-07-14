# Synthesus — Site SEO & Social Kit

Everything needed to make `site/index.html` render correctly in Google, on
Twitter/X, on LinkedIn, in Slack/Discord unfurls, and in iMessage previews.

**Canonical site URL used throughout this kit:**

```
https://str8biddness.github.io/synthesus/
```

That is the default GitHub Pages URL derived from the real remote
(`git@github.com:Str8biddness/synthesus.git` → owner `Str8biddness`, repo
`synthesus`; Pages lowercases the owner). If a custom domain is added later,
see section 4 — four values change, nothing else.

## Placeholders you MUST fill before launch

Two facts do not exist anywhere in this repo, so nothing here invented them.
Both appear as literal placeholder tokens in the JSON-LD below and **must** be
replaced before the site goes live:

| Token | What to put there |
| --- | --- |
| `PRICE_USD_REPLACE_ME` | The real one-time Gumroad price, as a decimal string, e.g. `"49.00"` |
| `https://GUMROAD_URL_REPLACE_ME` | The real Gumroad product URL |

Search for `REPLACE_ME` in `site/index.html` after pasting; there should be
zero hits when you are done.

---

## 1. `<meta>` / Open Graph / Twitter Card block

Paste this into the `<head>` of `site/index.html`, directly after the existing
`<meta charset>` and `<meta name="viewport">` tags.

`og:image` **must be an absolute URL** — relative paths (`og.png`,
`/og.png`) are silently dropped by Facebook, LinkedIn, Slack and Twitter.
Same for `og:url` and `canonical`.

```html
<!-- ── Primary meta ───────────────────────────────────────────── -->
<title>Synthesus — The AI that never leaves your machine.</title>
<meta name="description" content="A privacy-first Synthetic Intelligence OS that runs 100% locally on your own machine. It answers from your own documents and cites the source of every claim. Nothing is uploaded to any cloud. One-time purchase, no subscription.">
<link rel="canonical" href="https://str8biddness.github.io/synthesus/">
<meta name="theme-color" content="#070A10">

<!-- ── Open Graph (Facebook, LinkedIn, Slack, Discord, iMessage) ─ -->
<meta property="og:type" content="website">
<meta property="og:site_name" content="Synthesus">
<meta property="og:title" content="Synthesus — The AI that never leaves your machine.">
<meta property="og:description" content="A privacy-first Synthetic Intelligence OS that runs 100% locally on your own machine. It answers from your own documents and cites the source of every claim. Nothing is uploaded to any cloud.">
<meta property="og:url" content="https://str8biddness.github.io/synthesus/">
<meta property="og:image" content="https://str8biddness.github.io/synthesus/og.png">
<meta property="og:image:type" content="image/png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Synthesus — The AI that never leaves your machine.">
<meta property="og:locale" content="en_US">

<!-- ── Twitter / X ──────────────────────────────────────────────── -->
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Synthesus — The AI that never leaves your machine.">
<meta name="twitter:description" content="A privacy-first Synthetic Intelligence OS that runs 100% locally on your own machine. It answers from your own documents and cites the source of every claim.">
<meta name="twitter:image" content="https://str8biddness.github.io/synthesus/og.png">
<meta name="twitter:image:alt" content="Synthesus — The AI that never leaves your machine.">
```

Every claim above is drawn only from the product facts: 100% local, nothing
uploaded, grounded in the user's own documents, cites every claim, one-time
purchase.

---

## 2. JSON-LD structured data (schema.org `SoftwareApplication`)

Paste this at the end of the `<head>` of `site/index.html`. It is valid JSON
(validated — see the repo PR proof). Remember to replace the two `REPLACE_ME`
tokens.

```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "Synthesus",
  "description": "A privacy-first Synthetic Intelligence OS that runs 100% locally on the user's own machine. Nothing is uploaded to any cloud. It answers questions grounded in the user's own documents and cites the source of every claim. It generates images deterministically on CPU in about a second. It has a built-in local voice.",
  "url": "https://str8biddness.github.io/synthesus/",
  "image": "https://str8biddness.github.io/synthesus/og.png",
  "applicationCategory": "UtilitiesApplication",
  "applicationSubCategory": "Artificial Intelligence",
  "operatingSystem": "Linux",
  "softwareRequirements": "Linux (tested on Linux Mint and Ubuntu)",
  "isAccessibleForFree": false,
  "license": "https://www.gnu.org/licenses/agpl-3.0.html",
  "offers": {
    "@type": "Offer",
    "@id": "https://GUMROAD_URL_REPLACE_ME",
    "url": "https://GUMROAD_URL_REPLACE_ME",
    "price": "PRICE_USD_REPLACE_ME",
    "priceCurrency": "USD",
    "availability": "https://schema.org/InStock",
    "category": "One-time purchase"
  },
  "featureList": [
    "Runs 100% locally — nothing is uploaded to any cloud",
    "Answers grounded in your own documents, with a source citation for every claim",
    "Deterministic CPU image generation in about a second (not diffusion)",
    "Built-in local voice",
    "Optional, opt-in local neural add-ons (Real-ESRGAN sharpening, Piper voice) that download once from official sources with explicit consent, then run offline"
  ]
}
</script>
```

Notes on the choices:

- `operatingSystem: "Linux"` — the only platform claimed (Mint/Ubuntu tested).
- `isAccessibleForFree: false` + a single `Offer` — it is a paid one-time
  purchase, not a subscription, so there is deliberately **no**
  `priceSpecification` with a `billingDuration`.
- `license` points at AGPL-3.0, which covers the open-source core on GitHub.
- Validate any edits at <https://validator.schema.org/> before shipping.

---

## 3. `robots.txt` and `sitemap.xml`

Both live at the site root and are already committed:

- `site/robots.txt` — allows all crawlers, points at the sitemap.
- `site/sitemap.xml` — one `<url>` entry for the single-page site.

Bump `<lastmod>` in `site/sitemap.xml` whenever the page content meaningfully
changes.

---

## 4. What to change when a custom domain is added

Adding a custom domain (e.g. `synthesus.ai`) means adding a `site/CNAME` file
containing the bare domain and pointing DNS at GitHub Pages. Then **four**
values must be updated — every one of them is currently the
`https://str8biddness.github.io/synthesus/` Pages URL:

| # | File | Line / key | Change to |
| --- | --- | --- | --- |
| 1 | `site/robots.txt` | `Sitemap:` | `https://NEW-DOMAIN/sitemap.xml` |
| 2 | `site/sitemap.xml` | `<loc>` | `https://NEW-DOMAIN/` |
| 3 | `site/index.html` | `<link rel="canonical">` | `https://NEW-DOMAIN/` |
| 4 | `site/index.html` | `og:url`, `og:image`, `twitter:image` | `https://NEW-DOMAIN/` and `https://NEW-DOMAIN/og.png` |

Find every stale reference in one shot:

```bash
grep -rn "str8biddness.github.io" site/ docs/
```

That command must return zero hits once the migration is done. After the
switch, re-scrape the card in the
[Facebook Sharing Debugger](https://developers.facebook.com/tools/debug/) and
[LinkedIn Post Inspector](https://www.linkedin.com/post-inspector/) — both
cache aggressively and will otherwise keep serving the old URL.

---

## 5. Regenerating `og.png` from `social-card.html`

`site/social-card.html` is the **source** for the social card. It is a
self-contained 1200×630 HTML page with zero external requests (no webfonts, no
CDN, no remote images — system font stack and inline CSS only), so it renders
identically offline.

Neither Claude nor any LLM can emit a PNG directly. The PNG is produced by
screenshotting that page with a headless browser. From the repo root:

```bash
chromium --headless --disable-gpu --screenshot=site/og.png \
  --window-size=1200,630 --default-background-color=070A10FF \
  --hide-scrollbars site/social-card.html
```

Verify the result:

```bash
file site/og.png
# site/og.png: PNG image data, 1200 x 630, 8-bit/color RGB, non-interlaced
```

**Version gotcha:** older docs pass `--default-background-color=0`. Chromium
149 rejects that (`Expected a hex RGB or RGBA value`). Pass the 8-digit hex
`070A10FF` (the brand near-black, fully opaque) as shown above. On systems
where the binary is named differently, substitute `chromium-browser`,
`google-chrome`, or `google-chrome-stable`.

The committed `site/og.png` was generated by exactly this command and is
1200×630. Re-run it and re-commit the PNG any time `social-card.html` changes.
