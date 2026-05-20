#!/usr/bin/env python3
"""
lighthouse.py - Core Web Vitals + Lighthouse audits for the SEO plugin.

Lighthouse is a Node tool; we shell out to `npx -y lighthouse`. Lighthouse lab
numbers are noisy, so each form factor is run N times and the per-metric
*median* is kept. Runs mobile + desktop because the rubric sets separate
performance targets (mobile >=70, desktop >=90) and Google uses mobile-first
indexing.

Chrome optional: if Chrome/npx/lighthouse is unavailable the run is skipped
cleanly and lh.json records why, so checks.py emits SKIPPED instead of failing.
Python 3 stdlib only.
"""

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile

# Audit ids checks.py cares about (Lighthouse covers robots/meta/speed/mobile).
KEEP_AUDITS = [
    "largest-contentful-paint", "cumulative-layout-shift",
    "total-blocking-time", "first-contentful-paint", "speed-index",
    "interactive", "max-potential-fid", "server-response-time",
    "uses-responsive-images", "modern-image-formats", "offscreen-images",
    "unminified-javascript", "unminified-css", "unused-javascript",
    "unused-css-rules", "render-blocking-resources", "uses-text-compression",
    "uses-long-cache-ttl", "efficient-animated-content", "font-display",
    "viewport", "document-title", "meta-description", "http-status-code",
    "is-crawlable", "robots-txt", "canonical", "image-alt", "link-text",
    "crawlable-anchors", "tap-targets", "font-size", "content-width",
    "structured-data", "hreflang", "is-on-https", "redirects",
]


def find_chrome(explicit=None):
    if explicit and os.path.exists(explicit):
        return explicit
    env = os.environ.get("CHROME_PATH")
    if env and os.path.exists(env):
        return env
    import platform
    s = platform.system()
    if s == "Darwin":
        cands = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                 "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    elif s == "Windows":
        pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        pf86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        cands = [os.path.join(pf, r"Google\Chrome\Application\chrome.exe"),
                 os.path.join(pf86, r"Google\Chrome\Application\chrome.exe")]
    else:
        cands = [shutil.which(n) for n in
                 ("google-chrome", "google-chrome-stable", "chromium",
                  "chromium-browser")]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def npx_path():
    return shutil.which("npx")


def run_once(url, form_factor, chrome_bin, timeout):
    """One Lighthouse run -> parsed dict, or None on failure."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        out_path = tf.name
    try:
        cmd = [
            npx_path(), "-y", "lighthouse", url,
            "--quiet", "--output=json", f"--output-path={out_path}",
            "--only-categories=performance,seo,best-practices,accessibility",
            "--chrome-flags=--headless=new --no-sandbox --disable-gpu",
            "--max-wait-for-load=45000",
        ]
        if form_factor == "desktop":
            cmd.append("--preset=desktop")
        else:
            cmd += ["--form-factor=mobile", "--screenEmulation.mobile=true"]
        env = dict(os.environ)
        if chrome_bin:
            env["CHROME_PATH"] = chrome_bin
        subprocess.run(cmd, capture_output=True, text=True,
                       timeout=timeout, env=env)
        with open(out_path, "r", encoding="utf-8") as f:
            lh = json.load(f)
        return parse_lh(lh)
    except Exception:
        return None
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass


def parse_lh(lh):
    cats = lh.get("categories", {})
    audits = lh.get("audits", {})
    scores = {k: (cats.get(k, {}).get("score")) for k in
              ("performance", "seo", "best-practices", "accessibility")}
    kept = {}
    for aid in KEEP_AUDITS:
        a = audits.get(aid)
        if not a:
            continue
        kept[aid] = {
            "score": a.get("score"),
            "title": a.get("title"),
            "displayValue": a.get("displayValue"),
            "numericValue": a.get("numericValue"),
        }
    return {"scores": scores, "audits": kept,
            "lhVersion": lh.get("lighthouseVersion")}


def median_or_none(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def aggregate(runs):
    """Median across successful runs for scores + key numeric metrics."""
    ok = [r for r in runs if r]
    if not ok:
        return None
    scores = {}
    for k in ("performance", "seo", "best-practices", "accessibility"):
        scores[k] = median_or_none([r["scores"].get(k) for r in ok])
    audits = {}
    all_ids = set()
    for r in ok:
        all_ids |= set(r["audits"].keys())
    for aid in all_ids:
        nums = [r["audits"][aid].get("numericValue")
                for r in ok if aid in r["audits"]]
        scs = [r["audits"][aid].get("score")
               for r in ok if aid in r["audits"]]
        sample = next(r["audits"][aid] for r in ok if aid in r["audits"])
        audits[aid] = {
            "score": median_or_none(scs),
            "numericValue": median_or_none(nums),
            "title": sample.get("title"),
            "displayValue": sample.get("displayValue"),
        }
    return {"scores": scores, "audits": audits, "runs": len(ok),
            "lhVersion": ok[0].get("lhVersion")}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Lighthouse CWV -> lh.json")
    ap.add_argument("url")
    ap.add_argument("--out", default="lh.json")
    ap.add_argument("--runs", type=int, default=2,
                    help="runs per form factor; median taken (default 2)")
    ap.add_argument("--timeout", type=int, default=120,
                    help="seconds per Lighthouse run")
    ap.add_argument("--chrome-path", default=None)
    ap.add_argument("--form-factors", default="mobile,desktop",
                    help="comma list: mobile,desktop")
    args = ap.parse_args(argv)

    result = {"schema": 1, "tool": "lighthouse.py", "url": args.url,
              "available": False, "reason": None, "form_factors": {}}

    if not npx_path():
        result["reason"] = "npx (Node) not found - Lighthouse unavailable"
    elif not find_chrome(args.chrome_path):
        result["reason"] = "Chrome not found - Lighthouse requires Chrome"
    else:
        chrome_bin = find_chrome(args.chrome_path)
        ffs = [f.strip() for f in args.form_factors.split(",") if f.strip()]
        any_ok = False
        for ff in ffs:
            runs = [run_once(args.url, ff, chrome_bin, args.timeout)
                    for _ in range(max(1, args.runs))]
            agg = aggregate(runs)
            if agg:
                any_ok = True
                result["form_factors"][ff] = agg
            else:
                result["form_factors"][ff] = {"error": "all runs failed"}
        result["available"] = any_ok
        if not any_ok:
            result["reason"] = "all Lighthouse runs failed (see Chrome/network)"

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    if result["available"]:
        bits = []
        for ff, d in result["form_factors"].items():
            if "scores" in d:
                p = d["scores"].get("performance")
                bits.append(f"{ff}:perf={round(p*100) if p is not None else '?'}")
        print(f"lighthouse -> {args.out}  ({', '.join(bits)})")
    else:
        print(f"lighthouse -> {args.out}  (skipped: {result['reason']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
