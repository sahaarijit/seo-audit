---
name: seo-on-page-meta
description: "Use when a user is working on on-page SEO metadata or social previews - title tag, meta description, canonical, meta robots/noindex, viewport, Open Graph, or Twitter/X cards - especially as a follow-up to an /seo-audit:seo-audit report, or to do a best-effort meta audit when the audit engine cannot run on this surface. Triggers on 'fix my meta tags', 'my link preview looks wrong on Twitter/LinkedIn', 'add Open Graph to my Next.js app', 'why is my page noindex', 'title too long'."
---

# SEO: On-Page Meta & Social Previews

This skill covers what search engines and social platforms read from the
page `<head>`. Thresholds and pass/fail live in `scripts/checks.py` and the
generated report - do not restate them. Your job: interpret the findings and
give the user the exact `<head>` change for *their* framework, or run a
best-effort manual pass when the engine can't.

## Reading the audit output

Relevant `part` values in `findings.json`: **Meta Tags** and
**Open Graph & Social**. Checks: Title tag, Meta description, Canonical,
Meta robots (indexable), Viewport, Open Graph tags, Twitter card tags.

Priority order:
1. `FAIL` Meta robots = noindex on a page meant to rank - **highest impact**,
   the page is being actively excluded. Confirm it's not intentional.
2. `FAIL` Viewport missing - mobile rankings penalty + broken mobile layout.
3. `FAIL` Title / Meta description missing.
4. `FAIL` Open Graph (esp. missing `og:image`) - link previews look broken.
5. `WARN` length/format issues, Twitter card, canonical.

## Tailoring the fix to the user's stack

Detect the framework first, then give the concrete edit:

**Next.js (App Router)** - the Metadata API, not raw `<head>`:
- Static: export `metadata` from `layout.tsx`/`page.tsx` (`title`,
  `description`, `alternates.canonical`, `robots`, `openGraph`, `twitter`).
- Dynamic: `generateMetadata()`.
- `openGraph.images` / `twitter.card: 'summary_large_image'` for previews.
- Viewport: the `viewport` export (Next 14+) or default (Next injects one).

**Next.js (Pages Router)**: `next/head` `<Head>` in `_app`/page; or
`next-seo` (`<NextSeo>` / `DefaultSeo`).

**Nuxt 3 / Vue**: `useSeoMeta()` / `useHead()` (title, description,
ogTitle, ogImage, twitterCard...). **Astro**: set `<head>` in the layout or
use `astro-seo` (`<SEO>`). **SvelteKit**: `<svelte:head>` per route +
`+layout` defaults.

**WordPress**: Yoast SEO / Rank Math - the per-page "Social" tab sets
OG/Twitter; the SEO title/description templates set title/description. Tell
the user where in the editor, not raw HTML.

**Plain static / Vite / CRA**: edit `<head>` directly. For client-only React
SPAs, note that crawlers may not run JS reliably - prefer pre-render/SSG
(or `react-helmet-async` with SSR) so meta is in the initial HTML.

Image specs to pass on for previews: `og:image` 1200x630 (1.91:1), absolute
**https** URL; `twitter:card = summary_large_image` with a ~1200x628 image.
A relative or `http://` `og:image` is the single most common preview bug.

## Degraded surface: manual best-effort audit

If the engine couldn't run, fetch the page with your native tool (render JS
if the tool can) and inspect the `<head>` yourself, reporting in the same
`{check, status, evidence, fix}` shape:

- `<title>` present, single, concise, not a generic "Home | Site".
- `<meta name="description">` present and a reasonable length.
- `<link rel="canonical">` present and an absolute https URL.
- `<meta name="robots">` - flag any `noindex` hard.
- `<meta name="viewport" content="width=device-width, initial-scale=1">`.
- `og:title/description/image/url` (+ `og:type`, `og:site_name`);
  `og:image` absolute https.
- `twitter:card` (prefer `summary_large_image`), `twitter:title`,
  `twitter:description`, `twitter:image`.

State clearly it's a degraded manual pass; recommend re-running
`/seo-audit:seo-audit` on Claude Code / Desktop Local for the
deterministic result. For cache-stuck previews, point users at the
platform debuggers (Facebook Sharing Debugger, LinkedIn Post Inspector) to
force a re-scrape after the fix.
