---
name: seo-performance-mobile
description: "Use when a user is working on site speed, Core Web Vitals (LCP, CLS, INP/TBT), Lighthouse performance, or mobile usability (viewport, tap targets, font size, responsive layout) - especially as a follow-up to an /seo-audit:seo-audit report, or to reason about performance/mobile SEO when the audit engine cannot run on this surface. Triggers on 'my LCP is bad', 'improve PageSpeed score', 'fix Cumulative Layout Shift', 'site is slow on mobile', 'tap targets too small', 'Core Web Vitals failing'."
---

# SEO: Performance & Mobile

Speed and mobile usability are ranking factors (mobile-first indexing).
Numbers and thresholds come from Lighthouse via `scripts/lighthouse.py` and
the report - do not restate them. Your job: interpret the Core Web Vitals
findings, map them to the highest-leverage fix for *this* codebase, and
explain the degraded case when Lighthouse can't run.

## Reading the audit output

Relevant `part`: **Site Speed & Core Web Vitals** and **Mobile Usability**.
Checks: LCP, CLS, Responsiveness (TBT as the lab proxy for INP), Performance
score (mobile target >=70, desktop >=90), Speed opportunities, and the mobile
checks (viewport, tap targets, font size, content width).

Important interpretation notes:
- **TBT is a lab proxy for INP/FID**, not field INP. If the report shows TBT
  fine but the user reports jank, point them to Search Console's Core Web
  Vitals report (real-user field INP) - say this explicitly, don't conflate.
- If `Core Web Vitals` is `SKIPPED`, Lighthouse didn't run on this surface
  (no Chrome/Node). The structural findings are still valid; only live CWV
  is missing. Don't guess numbers.
- "Speed opportunities" lists *which* Lighthouse opportunities fired - tie
  each to a concrete fix below rather than dumping the list back.

Fix by symptom, highest leverage first:
1. **Poor LCP** - almost always the hero image or a render-blocking
   resource. Biggest single win.
2. **Poor CLS** - unsized media, late-loading fonts, injected banners/ads.
3. **High TBT** - heavy/third-party JS on the main thread.

## Tailoring the fix to the user's stack

**LCP**
- Next.js: `next/image` with `priority` on the hero; `next/font` (self-host,
  no layout shift); avoid client components for above-the-fold content.
- Nuxt/Astro/SvelteKit: framework `<Image>`/asset pipeline; `<link
  rel="preload">` the LCP image; ship critical content server-rendered.
- WordPress: an image plugin (WebP/AVIF + resize), a caching/CDN plugin,
  remove render-blocking plugin CSS/JS.
- Any: serve WebP/AVIF, correctly sized; put static assets on a CDN with long
  cache TTLs; HTTP/2+.

**CLS**
- Always set `width`/`height` (or CSS `aspect-ratio`) on `<img>`/embeds.
- `font-display: swap` and preload the primary web font; reserve space for
  anything injected (cookie bars, ads).

**TBT / INP**
- Code-split (dynamic `import()`), defer non-critical and third-party scripts
  (analytics, chat), drop unused JS, break long tasks. Audit third-party
  weight first - it's usually the bulk.

**Mobile usability**
- Viewport meta (`width=device-width, initial-scale=1`) - non-negotiable.
- Tap targets >=48x48px with spacing; base font >=16px, line-height >=1.5;
  responsive layout (no fixed widths > screen); avoid intrusive full-screen
  interstitials (use a banner instead).

## Degraded surface: no Lighthouse

If `Core Web Vitals` is `SKIPPED` (hosted sandbox / no Chrome), do not
fabricate metrics. Instead:
- Use the structural signals that *are* in the report (render-blocking
  scripts in `<head>`, viewport presence) plus a static read of the page:
  hero image format/size, number of third-party scripts, fonts.
- Give the user the qualitative risk list and the fixes above.
- Tell them to get real numbers from `pagespeed.web.dev` (field + lab) or by
  re-running `/seo-audit:seo-audit` on Claude Code / Desktop Local, and
  to confirm field data in Search Console's Core Web Vitals report.
