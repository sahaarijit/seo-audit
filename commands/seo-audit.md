---
description: "Audit a website or web app's SEO visibility and produce a fix-ready HTML report. Use whenever the user gives a URL and asks why it isn't ranking, isn't found on Google, has weak SEO, or wants an SEO/visibility/discoverability check, meta-tag/Open-Graph/sitemap/robots/Core-Web-Vitals/mobile audit - even if they don't say the word 'SEO'. Invocation: /seo-visibility:seo-audit <URL>"
---

Run a complete, deterministic SEO visibility audit for the URL the user gave
and hand them a single HTML report with prioritized findings and copy-paste
fixes.

## Behavior rules (obey strictly)

- **Do not ask questions. Do not stop for confirmation.** Resolve the URL,
  run the pipeline, present the result.
- The URL is `$ARGUMENTS`. Trim whitespace. If it has no scheme, the engine
  adds `https://` itself - pass it through as-is.
- If `$ARGUMENTS` is empty: print
  `Usage: /seo-visibility:seo-audit <URL>` and stop. Do not prompt.
- The Python scripts are the source of truth for pass/fail. Your job is to
  run them, then explain and tailor the fixes - never invent or override a
  verdict.

## Step 1 - find a Python interpreter

Run, in order, until one prints a version:

```
python3 --version
python --version
```

Use whichever worked as `PYBIN` below. If neither exists, tell the user:

> The local audit engine needs Python 3.8+ on PATH. Install it
> (Windows: python.org, tick "Add Python to PATH"), then re-run.
> I can still do a best-effort manual audit - see the seo-on-page-meta /
> seo-indexing-infra / seo-performance-mobile skills.

Then stop (or do the degraded manual audit if the user wants one).

## Step 2 - run the pipeline (one command)

```
PYBIN "${CLAUDE_PLUGIN_ROOT}/scripts/run.py" "<URL>"
```

This crawls once, renders with local Chrome if present, runs Lighthouse for
Core Web Vitals (skipped cleanly if Chrome/Node absent), evaluates every
check, and writes the report. It always finishes with two stable lines:

```
REPORT: <absolute path to report.html>
FINDINGS: <absolute path to findings.json>
```

Notes:
- First run may take ~30-60s extra the first time (`npx` fetches Lighthouse).
- Add `--quick` for a faster single Lighthouse pass, or `--no-lighthouse`
  if the user only wants the structural checks.
- A `fidelity=degraded` line means no Chrome/Lighthouse on this surface; the
  report is still valid for everything except live Core Web Vitals - say so.

## Step 3 - open and summarize

- Open the report for the user (best-effort, ignore failure):
  macOS `open "<REPORT>"` &middot; Linux `xdg-open "<REPORT>"` &middot;
  Windows `start "" "<REPORT>"`. Always also print the `REPORT:` path so
  they can open it manually.
- Read `FINDINGS` json and give a tight inline summary: the
  `fidelity`, the counts, and the FAIL items first (these are the
  likely reasons the site is hard to find), then WARN, then a one-line
  note that MANUAL items (Search Console / Bing / IndexNow) are
  account-bound and need their setup steps.
- Keep it scannable. The HTML report has the detail; don't repeat it all.

## Step 4 - offer targeted fix help

Point the user at the matching skill for stack-specific fixes (these tailor
the generic fix to Next.js / WordPress / Vercel / static / Webflow etc.):

- indexing / sitemap / robots / Search Console / Bing / IndexNow ->
  **seo-indexing-infra**
- title / description / canonical / viewport / Open Graph / Twitter ->
  **seo-on-page-meta**
- Core Web Vitals / speed / mobile usability -> **seo-performance-mobile**

Do not re-run the audit to answer a follow-up; read the existing
`findings.json` and consult the relevant skill.
