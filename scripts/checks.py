#!/usr/bin/env python3
"""
checks.py - deterministic SEO checkers -> findings.json

Reads snapshot.json (+ optional lh.json) and emits one findings.json. Every
threshold lives here so it is the single source of truth; the LLM never
decides pass/fail - it explains and tailors the fixes this script produces.

Finding shape:
  { part, module, check, status, evidence, fix, ref }
  status in: PASS | WARN | FAIL | SKIPPED | MANUAL

MANUAL = cannot be confirmed from outside the site (e.g. Search Console is
account-bound); we report the observable proxy and emit the setup steps
rather than fake a positive.

Python 3 stdlib only.
"""

import argparse
import json
import sys
from html.parser import HTMLParser
from urllib.parse import urlparse

# Own section taxonomy (the report groups findings by these).
SEC_DISCOVERY = "Search Engine Discovery"
SEC_BING = "Bing Webmaster Tools"
SEC_INDEXNOW = "IndexNow"
SEC_SITEMAP = "Sitemap"
SEC_ROBOTS = "Robots.txt"
SEC_META = "Meta Tags"
SEC_OG = "Open Graph & Social"
SEC_SPEED = "Site Speed & Core Web Vitals"
SEC_MOBILE = "Mobile Usability"


# --------------------------------------------------------------------------- #
# HTML extraction (stdlib parser - robust enough for head signals)
# --------------------------------------------------------------------------- #
class HeadParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = None
        self._in_title = False
        self.metas = []          # list of attr dicts
        self.links = []          # list of attr dicts
        self.html_lang = None
        self.scripts_total = 0
        self.scripts_blocking_head = 0
        self.imgs_total = 0
        self.imgs_missing_dims = 0
        self.imgs_legacy_format = 0
        self._in_head = False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html" and "lang" in a:
            self.html_lang = a["lang"].strip()
        elif tag == "head":
            self._in_head = True
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            self.metas.append(a)
        elif tag == "link":
            self.links.append(a)
        elif tag == "script":
            if a.get("src"):
                self.scripts_total += 1
                if self._in_head and "async" not in a and "defer" not in a \
                        and a.get("type", "") not in ("module",):
                    self.scripts_blocking_head += 1
        elif tag == "img":
            self.imgs_total += 1
            if not (a.get("width") and a.get("height")):
                self.imgs_missing_dims += 1
            src = (a.get("src") or "").lower()
            if src.endswith((".jpg", ".jpeg", ".png", ".gif")) \
                    and "data:" not in src:
                self.imgs_legacy_format += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "head":
            self._in_head = False

    def handle_data(self, data):
        if self._in_title:
            self.title = ((self.title or "") + data).strip()


def is_absolute_https(u):
    p = urlparse(u or "")
    return p.scheme == "https" and bool(p.netloc)


def find_meta(metas, *, name=None, prop=None):
    for m in metas:
        if name and m.get("name", "").lower() == name.lower():
            return m.get("content", "").strip()
        if prop and m.get("property", "").lower() == prop.lower():
            return m.get("content", "").strip()
    return None


def f(part, module, check, status, evidence, fix, ref):
    return {"part": part, "module": module, "check": check,
            "status": status, "evidence": evidence, "fix": fix, "ref": ref}


# --------------------------------------------------------------------------- #
# Module 1: seo-indexing-infra  (discovery, sitemap, robots)
# --------------------------------------------------------------------------- #
def check_indexing(snap, P):
    M = "seo-indexing-infra"
    out = []
    metas = P.metas
    origin = snap["origin"]

    # Google Search Console (account-bound -> proxy + setup)
    gsv = find_meta(metas, name="google-site-verification")
    out.append(f(
        SEC_DISCOVERY, M, "Search Console ownership signal", "MANUAL",
        ("google-site-verification meta tag found - one valid ownership method"
         if gsv else
         "No google-site-verification meta tag. Active Search Console "
         "monitoring cannot be confirmed from outside the site."),
        "Verify the property in Search Console, then submit the sitemap there:\n"
        "1. search.google.com/search-console -> Add property\n"
        "2. Verify (HTML tag is easiest):\n"
        '   <meta name="google-site-verification" content="YOUR-CODE">\n'
        f"3. Sitemaps -> submit {origin}/sitemap.xml\n"
        "4. Watch the Pages (Coverage) report for indexing/errors",
        "Discovery - Search Console"))

    # Bing Webmaster Tools (account-bound -> proxy + setup)
    msv = find_meta(metas, name="msvalidate.01")
    out.append(f(
        SEC_BING, M, "Bing ownership signal", "MANUAL",
        ("msvalidate.01 meta tag found - Bing ownership method present"
         if msv else
         "No msvalidate.01 meta tag. Bing setup not confirmable externally."),
        "bing.com/webmasters -> Import from Google Search Console (one click) "
        "OR add manually + verify. Bing also powers DuckDuckGo/Yahoo and "
        "often indexes faster - less competition than Google.",
        "Discovery - Bing Webmaster Tools"))

    # IndexNow (key file is secret -> cannot brute-detect)
    robots_body = (snap["robots"]["body"] or "").lower()
    hint = "indexnow" in robots_body
    out.append(f(
        SEC_INDEXNOW, M, "IndexNow instant-indexing", "MANUAL",
        ("robots.txt mentions IndexNow - likely configured; confirm the key "
         "file resolves" if hint else
         "Cannot detect the IndexNow key file from outside (the filename IS "
         "the secret key). Not a failure - just unverifiable remotely."),
        "1. Generate a key (UUID).\n"
        "2. Put it in {key}.txt at the site root so "
        f"{origin}/{{key}}.txt returns the key.\n"
        "3. On publish/update, GET "
        "https://api.indexnow.org/indexnow?url={page}&key={key}\n"
        "4. Automate in the deploy step. Bing/Yandex/Seznam/Naver honor it.",
        "Discovery - IndexNow"))

    # Sitemap
    sms = snap.get("sitemaps", [])
    good = [s for s in sms if s["ok"] and s["valid_xml"]]
    in_robots = bool(snap["robots"].get("sitemap_lines"))
    if good:
        big = [s for s in good if s["entry_count"] > 50000]
        st = "WARN" if big else "PASS"
        ev = "; ".join(f"{s['url']} ({s['kind']}, {s['entry_count']} entries)"
                       for s in good)
        if big:
            ev += " - exceeds the 50,000-URL-per-file limit"
        out.append(f(
            SEC_SITEMAP, M, "Sitemap present & valid", st, ev,
            "Keep <=50,000 URLs and <=50MB per file; use a sitemap index "
            "above that. Only canonical URLs, update lastmod on real changes.",
            "Technical - Sitemap"))
    else:
        tried = ", ".join(f"{s['url']} (HTTP {s['status']})" for s in sms) \
                or "no candidates"
        out.append(f(
            SEC_SITEMAP, M, "Sitemap present & valid", "FAIL",
            f"No valid sitemap found. Tried: {tried}",
            "Generate /sitemap.xml (next-sitemap, Yoast/Rank Math, "
            "gatsby-plugin-sitemap, Hugo built-in, etc.), reference it in "
            "robots.txt, and submit it in Search Console + Bing.",
            "Technical - Sitemap"))
    out.append(f(
        SEC_SITEMAP, M, "Sitemap referenced in robots.txt",
        "PASS" if in_robots else "WARN",
        ("robots.txt has a Sitemap: line" if in_robots else
         "robots.txt does not point to the sitemap"),
        "Add to robots.txt:  Sitemap: " + origin + "/sitemap.xml",
        "Technical - Sitemap discovery"))

    # robots.txt
    r = snap["robots"]
    if not r["ok"]:
        out.append(f(
            SEC_ROBOTS, M, "robots.txt present", "WARN",
            f"{r['url']} returned HTTP {r['status']} - no robots.txt",
            "Add /robots.txt. Minimal safe file:\n"
            "User-agent: *\nAllow: /\nSitemap: " + origin + "/sitemap.xml",
            "Technical - Robots.txt"))
    else:
        body = r["body"]
        lines = [ln.strip() for ln in body.splitlines()]
        low = body.lower()
        blanket = False
        ua_all = False
        for ln in lines:
            ll = ln.lower()
            if ll.startswith("user-agent:") and ll.split(":", 1)[1].strip() == "*":
                ua_all = True
            elif ll.startswith("user-agent:"):
                ua_all = False
            elif ua_all and ll.startswith("disallow:") \
                    and ll.split(":", 1)[1].strip() == "/":
                blanket = True
        blocks_assets = any(
            x in low for x in ("disallow: /css", "disallow: /js",
                               "disallow: /assets", "disallow: /_next"))
        if blanket:
            out.append(f(
                SEC_ROBOTS, M, "Not blocking the whole site",
                "FAIL", "robots.txt has `Disallow: /` for User-agent: * - "
                "this blocks the entire site from indexing",
                "Unless intentional, replace with:\nUser-agent: *\nAllow: /\n"
                "Sitemap: " + origin + "/sitemap.xml",
                "Technical - Robots.txt"))
        else:
            out.append(f(
                SEC_ROBOTS, M, "Not blocking the whole site",
                "PASS", "No site-wide Disallow: / for all bots", "-",
                "Technical - Robots.txt"))
        out.append(f(
            SEC_ROBOTS, M, "Not blocking CSS/JS",
            "WARN" if blocks_assets else "PASS",
            ("robots.txt appears to block CSS/JS/asset paths - search engines "
             "need these to render pages" if blocks_assets else
             "CSS/JS not blocked"),
            "Remove Disallow rules for /css, /js, /assets, /_next so crawlers "
            "can render the page.", "Technical - Robots.txt"))
    return out


# --------------------------------------------------------------------------- #
# Module 2: seo-on-page-meta  (meta tags, Open Graph, social)
# --------------------------------------------------------------------------- #
def check_on_page(snap, P):
    M = "seo-on-page-meta"
    out = []
    metas = P.metas
    title = P.title or ""

    # Title
    if not title:
        st, ev = "FAIL", "No <title> tag (or empty)"
    elif len(title) > 60:
        st, ev = "WARN", f"Title is {len(title)} chars (>60 gets truncated): \"{title}\""
    elif title.lower().startswith("home |") or title.lower().startswith("home -"):
        st, ev = "WARN", f"Generic 'Home |' style title: \"{title}\""
    else:
        st, ev = "PASS", f"{len(title)} chars: \"{title}\""
    out.append(f(
        SEC_META, M, "Title tag", st, ev,
        "<title>Primary Keyword - Compelling Benefit</title>  "
        "(<=60 chars, keyword first, unique per page). "
        'Bad: "Home | Site"  Good: "Acme Widgets - Fast Lightweight Toolkit"',
        "On-page - Title tag"))

    # Meta description
    desc = find_meta(metas, name="description")
    if not desc:
        st, ev = "FAIL", "No meta description"
    elif len(desc) > 160:
        st, ev = "WARN", f"Description is {len(desc)} chars (>160 truncated)"
    else:
        st, ev = "PASS", f"{len(desc)} chars"
    out.append(f(
        SEC_META, M, "Meta description", st, ev,
        '<meta name="description" content="<=160 chars, summarize the page, '
        'natural keywords, a call to action. Unique per page.">',
        "On-page - Meta description"))

    # Canonical
    canon = next((l.get("href") for l in P.links
                  if l.get("rel", "").lower() == "canonical"), None)
    if canon and is_absolute_https(canon):
        st, ev = "PASS", f"Canonical: {canon}"
    elif canon:
        st, ev = "WARN", f"Canonical present but not absolute https: {canon}"
    else:
        st, ev = "WARN", "No canonical tag"
    out.append(f(
        SEC_META, M, "Canonical tag", st, ev,
        '<link rel="canonical" href="https://yoursite.com/page"> - set the '
        "official URL when a page is reachable at multiple URLs (www/non-www, "
        "http/https, duplicates).", "On-page - Canonical"))

    # Meta robots (accidental noindex is severe)
    mrobots = (find_meta(metas, name="robots") or "").lower()
    if "noindex" in mrobots:
        st, ev = "FAIL", f'meta robots = "{mrobots}" - this page is set to NOINDEX'
    elif mrobots:
        st, ev = "PASS", f'meta robots = "{mrobots}"'
    else:
        st, ev = "PASS", "No meta robots (defaults to index,follow)"
    out.append(f(
        SEC_META, M, "Meta robots (indexable)", st, ev,
        "Remove noindex from pages you want ranked. index,follow is the "
        "default and needs no tag. Use noindex only on utility/private pages.",
        "On-page - Meta robots"))

    # Viewport (also a mobile signal - reported here and in mobile module)
    vp = find_meta(metas, name="viewport")
    ok_vp = vp and "width=device-width" in vp.replace(" ", "")
    out.append(f(
        SEC_META, M, "Viewport meta tag",
        "PASS" if ok_vp else "FAIL",
        (f'viewport = "{vp}"' if vp else "No viewport meta tag - "
         "site will look broken on mobile and lose mobile rankings"),
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "On-page - Viewport"))

    # Open Graph
    og_specs = [("og:title", True), ("og:description", True),
                ("og:image", True), ("og:url", True),
                ("og:type", False), ("og:site_name", False)]
    missing = [k for k, req in og_specs if not find_meta(metas, prop=k) and req]
    ogimg = find_meta(metas, prop="og:image")
    if missing:
        st = "FAIL" if "og:image" in missing else "WARN"
        ev = "Missing required OG tags: " + ", ".join(missing)
    elif ogimg and not is_absolute_https(ogimg):
        st, ev = "WARN", f"og:image is not absolute https: {ogimg}"
    else:
        st, ev = "PASS", "og:title/description/image/url present"
    out.append(f(
        SEC_OG, M, "Open Graph tags", st, ev,
        '<meta property="og:title" content="...">\n'
        '<meta property="og:description" content="...">\n'
        '<meta property="og:image" content="https://site/og.png">  '
        "(1200x630, 1.91:1, <8MB, absolute https)\n"
        '<meta property="og:url" content="https://site">\n'
        '<meta property="og:type" content="website">\n'
        '<meta property="og:site_name" content="...">',
        "Social - Open Graph"))

    # Twitter card
    tw_card = find_meta(metas, name="twitter:card")
    tw_missing = [k for k in ("twitter:card", "twitter:title",
                              "twitter:description", "twitter:image")
                  if not find_meta(metas, name=k)]
    if tw_missing:
        st, ev = "WARN", "Missing Twitter card tags: " + ", ".join(tw_missing)
    elif tw_card and tw_card != "summary_large_image":
        st, ev = "WARN", f'twitter:card="{tw_card}" (summary_large_image recommended)'
    else:
        st, ev = "PASS", "Twitter card tags present (summary_large_image)"
    out.append(f(
        SEC_OG, M, "Twitter card tags", st, ev,
        '<meta name="twitter:card" content="summary_large_image">\n'
        '<meta name="twitter:title" content="...">\n'
        '<meta name="twitter:description" content="...">\n'
        '<meta name="twitter:image" content="https://site/twitter.png">  '
        "(1200x628 recommended)",
        "Social - Twitter card"))
    return out


# --------------------------------------------------------------------------- #
# Module 3: seo-performance-mobile  (speed, Core Web Vitals, mobile)
# --------------------------------------------------------------------------- #
def _cwv_status(val, good, poor):
    if val is None:
        return "SKIPPED"
    if val <= good:
        return "PASS"
    if val <= poor:
        return "WARN"
    return "FAIL"


def check_perf_mobile(snap, P, lh):
    M = "seo-performance-mobile"
    out = []

    if not lh or not lh.get("available"):
        reason = (lh or {}).get("reason", "Lighthouse not run")
        out.append(f(
            SEC_SPEED, M, "Core Web Vitals", "SKIPPED",
            f"Lighthouse unavailable: {reason}. DOM heuristics below still run.",
            "Run on a surface with Chrome (Claude Code / Desktop Local) for "
            "real LCP/CLS numbers, or test at pagespeed.web.dev.",
            "Core Web Vitals"))
        # DOM-only heuristics so the section is never empty
        out.append(f(
            SEC_SPEED, M, "Render-blocking scripts in <head>",
            "WARN" if P.scripts_blocking_head else "PASS",
            f"{P.scripts_blocking_head} blocking <script src> in <head> "
            f"(of {P.scripts_total} total)",
            "Add defer/async to non-critical scripts; move below the fold; "
            "code-split large bundles.", "Performance - JavaScript"))
        out.append(f(
            SEC_MOBILE, M, "Viewport meta tag",
            "PASS" if find_meta(P.metas, name="viewport") else "FAIL",
            ("viewport present" if find_meta(P.metas, name="viewport")
             else "no viewport meta tag"),
            '<meta name="viewport" content="width=device-width, '
            'initial-scale=1">', "Mobile - Viewport"))
        return out

    # Core Web Vitals - mobile is the indexing form factor; report it.
    mob = lh["form_factors"].get("mobile", {})
    desk = lh["form_factors"].get("desktop", {})
    aud = mob.get("audits", {})

    lcp_ms = aud.get("largest-contentful-paint", {}).get("numericValue")
    lcp_s = (lcp_ms / 1000.0) if lcp_ms is not None else None
    out.append(f(
        SEC_SPEED, M, "LCP (Largest Contentful Paint, mobile)",
        _cwv_status(lcp_s, 2.5, 4.0),
        f"LCP = {lcp_s:.2f}s (good <2.5s, poor >4s)" if lcp_s is not None
        else "LCP unavailable",
        "Optimize the hero image (WebP/AVIF, correct size, preload), cut "
        "render-blocking CSS/JS, use a CDN + caching.",
        "Core Web Vitals - LCP"))

    cls = aud.get("cumulative-layout-shift", {}).get("numericValue")
    out.append(f(
        SEC_SPEED, M, "CLS (Cumulative Layout Shift, mobile)",
        _cwv_status(cls, 0.1, 0.25),
        f"CLS = {cls:.3f} (good <0.1, poor >0.25)" if cls is not None
        else "CLS unavailable",
        "Set width/height (or aspect-ratio) on images/embeds; reserve space "
        "for ads/banners; preload fonts with font-display: swap.",
        "Core Web Vitals - CLS"))

    tbt = aud.get("total-blocking-time", {}).get("numericValue")
    out.append(f(
        SEC_SPEED, M, "Responsiveness (TBT, INP lab proxy)",
        _cwv_status(tbt, 200, 600),
        (f"TBT = {tbt:.0f}ms - lab proxy for INP/FID "
         "(field INP target <200ms; confirm in Search Console CWV)"
         if tbt is not None else "TBT unavailable"),
        "Minimize/defer JS, remove unused code, code-split, break up long "
        "tasks.", "Core Web Vitals - INP/TBT"))

    # PageSpeed score targets
    for ff, want, d in (("mobile", 0.70, mob), ("desktop", 0.90, desk)):
        sc = (d.get("scores") or {}).get("performance")
        if sc is None:
            continue
        out.append(f(
            SEC_SPEED, M, f"Performance score ({ff})",
            "PASS" if sc >= want else "WARN",
            f"{ff} performance = {round(sc*100)} "
            f"(target: {'>=90' if ff=='desktop' else '>=70'})",
            "Work the failing Lighthouse opportunities (images, JS, CSS, "
            "caching, fonts).", "Performance - score"))

    # Surface failing Lighthouse opportunities mapped to the fix list
    fixmap = {
        "modern-image-formats": "Serve WebP/AVIF instead of JPG/PNG",
        "uses-responsive-images": "Size images to their displayed size",
        "offscreen-images": "Lazy-load below-the-fold images",
        "render-blocking-resources": "Defer/inline critical CSS, defer JS",
        "unminified-javascript": "Minify JavaScript",
        "unminified-css": "Minify CSS",
        "unused-javascript": "Remove/code-split unused JS",
        "unused-css-rules": "Remove unused CSS",
        "uses-text-compression": "Enable gzip/brotli compression",
        "uses-long-cache-ttl": "Set long cache TTLs (CDN/caching)",
        "font-display": "Use font-display: swap for custom fonts",
    }
    failing = []
    for aid, label in fixmap.items():
        a = aud.get(aid)
        if a and a.get("score") is not None and a["score"] < 0.9:
            failing.append(f"{label}")
    out.append(f(
        SEC_SPEED, M, "Speed opportunities",
        "WARN" if failing else "PASS",
        ("; ".join(failing) if failing else
         "No major Lighthouse speed opportunities flagged"),
        "Apply the listed fixes (images / JavaScript / CSS / hosting / "
        "fonts).", "Performance - opportunities"))

    # Mobile usability (Lighthouse audits, mobile form factor)
    for aid, name, fix in (
        ("viewport", "Viewport configured",
         '<meta name="viewport" content="width=device-width, '
         'initial-scale=1">'),
        ("tap-targets", "Tap targets >=48px",
         "Make buttons/links >=48x48px with spacing between them"),
        ("font-size", "Legible base font (>=16px)",
         "Base font >=16px, line-height >=1.5, no zoom required"),
        ("content-width", "Content fits viewport (no h-scroll)",
         "Responsive layout, no fixed widths wider than the screen"),
    ):
        a = aud.get(aid)
        if not a or a.get("score") is None:
            continue
        out.append(f(
            SEC_MOBILE, M, name,
            "PASS" if a["score"] >= 0.9 else "WARN",
            a.get("displayValue") or a.get("title") or aid,
            fix, "Mobile - usability"))
    return out


# --------------------------------------------------------------------------- #
def run_checks(snap, lh):
    html = (snap.get("rendered", {}).get("html")
            or snap.get("raw", {}).get("html") or "")
    P = HeadParser()
    try:
        P.feed(html)
    except Exception:
        pass
    findings = []
    findings += check_indexing(snap, P)
    findings += check_on_page(snap, P)
    findings += check_perf_mobile(snap, P, lh)

    counts = {"PASS": 0, "WARN": 0, "FAIL": 0, "SKIPPED": 0, "MANUAL": 0}
    for x in findings:
        counts[x["status"]] = counts.get(x["status"], 0) + 1

    render_engine = snap.get("rendered", {}).get("engine") or "raw-only"
    return {
        "schema": 1,
        "tool": "checks.py",
        "url": snap.get("final_url"),
        "fetched_at": snap.get("fetched_at"),
        "render_mode": render_engine,
        "lighthouse": bool(lh and lh.get("available")),
        "fidelity": ("full" if render_engine == "chrome"
                     and lh and lh.get("available") else "degraded"),
        "summary": counts,
        "findings": findings,
        "engine_warnings": snap.get("warnings", []),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="snapshot(+lh) -> findings.json")
    ap.add_argument("snapshot", help="snapshot.json path")
    ap.add_argument("--lh", default=None, help="lh.json path (optional)")
    ap.add_argument("--out", default="findings.json")
    args = ap.parse_args(argv)

    with open(args.snapshot, encoding="utf-8") as fh:
        snap = json.load(fh)
    lh = None
    if args.lh:
        try:
            with open(args.lh, encoding="utf-8") as fh:
                lh = json.load(fh)
        except FileNotFoundError:
            lh = None

    result = run_checks(snap, lh)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    s = result["summary"]
    print(f"findings -> {args.out}  (fidelity={result['fidelity']}, "
          f"PASS={s['PASS']} WARN={s['WARN']} FAIL={s['FAIL']} "
          f"SKIPPED={s['SKIPPED']} MANUAL={s['MANUAL']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
