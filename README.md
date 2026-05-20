# SEO Visibility

Audit any website or web app's SEO and get a single, fix-ready HTML report:
indexing infrastructure (sitemap, robots.txt, Search Console / Bing /
IndexNow), on-page meta (title, description, canonical, viewport, Open Graph,
Twitter cards), Core Web Vitals, and mobile usability.

Findings are produced by deterministic checks - the verdicts are not guessed.
The three bundled skills add stack-specific fix guidance (Next.js, Nuxt,
Astro, WordPress, static, …) as follow-up.

## Installation

Works in Claude Code (CLI), Claude Desktop, and any surface that supports
Claude Code plugins. Pick one of the install paths below; then restart the
Claude Code session so the new command and skills load.

### From GitHub (recommended once published)

```
/plugin marketplace add sahaarijit/seo-audit
/plugin install seo-audit@seo-audit
```

The first command adds this repo as a single-plugin marketplace; the second
installs the plugin from it. `seo-audit@seo-audit` =
`<plugin-name>@<marketplace-name>` - both are `seo-audit` because the
marketplace ships exactly this one plugin.

### From a local clone (development / offline)

```
git clone https://github.com/sahaarijit/seo-audit ~/Projects/seo-audit
/plugin marketplace add ~/Projects/seo-audit
/plugin install seo-audit@seo-audit
```

Point `marketplace add` at the directory that contains `.claude-plugin/` (the
plugin root). Local changes are picked up on the next session restart.

### From the zip distributable

```
unzip seo-audit-<version>.zip -d ~/Projects/
/plugin marketplace add ~/Projects/seo-audit
/plugin install seo-audit@seo-audit
```

### Verify the install

```
/plugin
/seo-audit:seo-audit https://example.com
```

`/plugin` lists installed plugins (you should see `seo-audit`); the
command then runs an end-to-end audit and opens the report.

## Updating

```
/plugin marketplace update seo-audit
/plugin install seo-audit@seo-audit      # reinstall to pick up the new version
```

For a local-clone install, `git pull` in the cloned directory, then
`/plugin marketplace update seo-audit` followed by restart.

## Uninstallation

```
/plugin uninstall seo-audit@seo-audit    # remove the plugin
/plugin marketplace remove seo-audit          # also remove the marketplace entry
```

Generated reports in `~/seo-audit-reports/` are **not** removed by
uninstall - delete that directory manually if you want them gone:

```
rm -rf ~/seo-audit-reports
```

The Lighthouse package that `npx` cached on first use lives under your npm
cache (`~/.npm/_npx`); leaving it does no harm, but
`npm cache clean --force` reclaims the space.

## Usage

```
/seo-audit:seo-audit https://example.com
```

Runs the pipeline (crawl once → render → Core Web Vitals → evaluate →
report), opens the HTML report, and summarizes the failures inline. Then ask
follow-ups like "fix the Open Graph issue in my Next.js app" and the matching
skill tailors the fix to your stack.

## Requirements

- **Python 3.8+** on `PATH` (the audit engine; no third-party packages).
  Windows: install from python.org and tick "Add Python to PATH".
- **Google Chrome** (recommended) - enables JS rendering and Core Web
  Vitals. If absent, the audit still runs and the report is valid for
  everything except live Core Web Vitals (it says so).
- **Node.js** - ships with Claude Code / Claude Desktop; used to run
  Lighthouse via `npx` (fetched on first use).

Best fidelity on Claude Code or Claude Desktop in **Local** mode (runs on
your machine). On hosted surfaces without Chrome the report degrades
gracefully and the skills can do a best-effort manual pass.

## Flags

- `--quick` – one Lighthouse pass, mobile only (faster)
- `--no-lighthouse` – structural checks only, skip Core Web Vitals
- `--no-chrome` – raw fetch only (no JS render)

## What you get

`report.html` plus `findings.json` (machine-readable) in
`~/seo-audit-reports/<host>_<timestamp>/`. Each finding has a status
(PASS / WARN / FAIL / SKIPPED / MANUAL), the evidence, and a copy-paste fix.
MANUAL items (Search Console / Bing / IndexNow) are account-bound and come
with setup steps rather than a remote pass/fail.
