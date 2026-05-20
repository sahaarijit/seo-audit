---
name: seo-indexing-infra
description: "Use when a user is working on search-engine discovery and indexing infrastructure - sitemaps, robots.txt, Google Search Console, Bing Webmaster Tools, or IndexNow - especially as a follow-up to an /seo-visibility:seo-audit report, or to do a best-effort indexing audit when the audit engine cannot run on this surface. Triggers on questions like 'why isn't Google indexing my site', 'fix my robots.txt', 'add a sitemap to my Next.js app', 'set up IndexNow', 'is my site discoverable'."
---

# SEO: Indexing & Discovery Infrastructure

This skill makes a site **discoverable and crawlable**: sitemap, robots.txt,
Search Console, Bing, IndexNow. It does not restate pass/fail thresholds -
`scripts/checks.py` and the generated report are the source of truth. Your job
here is to (1) interpret those findings and (2) give the user the exact change
for *their* stack, or (3) do a best-effort audit when the engine can't run.

## Reading the audit output

The report and `findings.json` (in the run's output dir) carry findings with
`{part, check, status, evidence, fix, ref}`. For this skill, the relevant
`part` values are: **Sitemap**, **Robots.txt**, **Search Engine Discovery**,
**Bing Webmaster Tools**, **IndexNow**.

Priority order when advising:
1. `FAIL` on Robots.txt "Not blocking the whole site" - nothing else matters
   if the site is blocked. Fix first.
2. `FAIL` Sitemap missing/invalid - search engines can't enumerate pages.
3. `WARN` sitemap-not-in-robots, robots.txt missing.
4. `MANUAL` Search Console / Bing / IndexNow - account-bound; walk the user
   through setup, don't claim they're "done" from outside.

## Tailoring the fix to the user's stack

Detect the stack from the repo (package.json, framework files) before
answering. The report's `fix` is generic; translate it:

**Sitemap**
- Next.js (App Router): `app/sitemap.ts` exporting a `MetadataRoute.Sitemap`;
  or `next-sitemap` with a `postbuild` script for large/dynamic sites.
- Next.js (Pages Router): `next-sitemap`, or a `getServerSideProps` route.
- Nuxt: `@nuxtjs/sitemap`. Astro: `@astrojs/sitemap` integration.
- Gatsby: `gatsby-plugin-sitemap`. Hugo: built-in (`sitemap` config).
- WordPress: Yoast SEO or Rank Math (both emit `/sitemap_index.xml` - point
  Search Console/robots at the index).
- Plain static / Vite / CRA: generate `public/sitemap.xml` at build, or a
  small script; ship absolute canonical URLs only.

**robots.txt**
- Next.js (App Router): `app/robots.ts` (`MetadataRoute.Robots`).
- Static hosts (Vercel/Netlify/Cloudflare Pages/GitHub Pages): a real file in
  the public/ root. Confirm it is served at `/robots.txt`, not rewritten.
- Always include the absolute `Sitemap:` line. Never `Disallow:` CSS/JS/asset
  dirs (`/_next`, `/assets`) - crawlers need them to render.

**Search Console / Bing** (MANUAL - guide the steps)
- Verification: HTML meta tag injected via the framework's head
  (Next.js metadata `verification`, Nuxt `useHead`, WordPress SEO plugin,
  static `<head>`), or a DNS TXT record (survives redeploys - prefer for
  domain-level).
- After verifying: submit the sitemap in Search Console, then one-click
  **Import** into Bing Webmaster Tools (it pulls the GSC config).

**IndexNow** (instant indexing for Bing/Yandex/Seznam/Naver)
- Cloudflare: enable IndexNow in the dashboard (zero code).
- WordPress: the IndexNow plugin (or Rank Math's built-in).
- Vercel/Netlify/Next.js: host `{key}.txt` at the site root (e.g.
  `public/{key}.txt`), then ping
  `https://api.indexnow.org/indexnow?url=...&key=...` from a deploy hook /
  `postbuild` step. Do not over-ping; only changed URLs.

## Degraded surface: manual best-effort audit

If the engine could not run (no Python/Chrome on this surface, e.g. a hosted
sandbox), do the audit yourself with your native web/fetch tool and report in
the same `{check, status, evidence, fix}` shape:

1. Fetch `https://HOST/robots.txt` - exists? any `Disallow: /` for
   `User-agent: *`? any blocked CSS/JS? a `Sitemap:` line?
2. Fetch the sitemap (from the robots `Sitemap:` line, else
   `/sitemap.xml`) - 200? valid XML? `<urlset>`/`<sitemapindex>`?
   reasonable URL count?
3. Fetch the homepage, inspect `<head>` for `google-site-verification` and
   `msvalidate.01` meta tags (observable proxies only - state plainly that
   Search Console/Bing activity itself can't be confirmed from outside).
4. IndexNow can't be detected remotely (the key file name *is* the secret) -
   say so; don't report a false negative.

Be explicit that this is a degraded manual pass and recommend re-running
`/seo-visibility:seo-audit` on Claude Code / Desktop Local for the full
deterministic result.
