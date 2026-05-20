#!/usr/bin/env python3
"""
run.py - single entrypoint that wires the SEO Visibility pipeline.

  seo_engine.py  -> snapshot.json   (fetch + Chrome render, robots, sitemaps)
  lighthouse.py  -> lh.json         (CWV, optional - tolerated if it fails)
  checks.py      -> findings.json   (deterministic findings, source of truth)
  report.py      -> report.html     (self-contained HTML)

Pure stdlib + pathlib so it is OS-agnostic. Re-invokes the *same* interpreter
(sys.executable) for each step so there is no python/python3 ambiguity. Always
produces a report when the page can be fetched at all - Lighthouse/Chrome
failures degrade gracefully instead of aborting.
"""

import argparse
import json
import pathlib
import subprocess
import sys
import time
from urllib.parse import urlparse

HERE = pathlib.Path(__file__).resolve().parent


def slug(url):
    netloc = urlparse(url if "//" in url else "https://" + url).netloc
    return "".join(c if c.isalnum() or c in "-." else "_" for c in netloc) \
        or "site"


def step(label, cmd):
    print(f"  - {label} ...", flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.stdout.strip():
        print("    " + r.stdout.strip().replace("\n", "\n    "))
    if r.returncode != 0 and r.stderr.strip():
        print("    " + r.stderr.strip().replace("\n", "\n    ")[:800])
    return r.returncode


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run the full SEO audit pipeline")
    ap.add_argument("url", help="site URL to audit")
    ap.add_argument("--out-dir", default=None,
                    help="output dir (default ~/seo-audit-reports/...)")
    ap.add_argument("--no-lighthouse", action="store_true",
                    help="skip Core Web Vitals (faster)")
    ap.add_argument("--no-chrome", action="store_true",
                    help="raw fetch only (no JS render, no Lighthouse)")
    ap.add_argument("--quick", action="store_true",
                    help="1 Lighthouse run, mobile only")
    ap.add_argument("--timeout", type=int, default=25)
    args = ap.parse_args(argv)

    py = sys.executable or "python3"
    url = args.url.strip()

    if args.out_dir:
        out = pathlib.Path(args.out_dir).expanduser().resolve()
    else:
        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        out = (pathlib.Path.home() / "seo-audit-reports"
               / f"{slug(url)}_{stamp}")
    out.mkdir(parents=True, exist_ok=True)

    snap = out / "snapshot.json"
    lh = out / "lh.json"
    findings = out / "findings.json"
    report = out / "report.html"

    print(f"SEO audit: {url}")
    print(f"output dir: {out}")

    eng = [py, str(HERE / "seo_engine.py"), url, "--out", str(snap),
           "--timeout", str(args.timeout)]
    if args.no_chrome:
        eng.append("--no-chrome")
    step("crawl + render", eng)
    if not snap.exists():
        print("FATAL: could not fetch the URL - nothing to report.")
        return 2
    # The engine writes a snapshot even on DNS/connection failure. The engine
    # sets reachable=False when the server never returned an HTTP status; bail
    # cleanly instead of emitting a bogus all-FAIL report for a dead host.
    try:
        sd = json.loads(snap.read_text())
        if sd.get("reachable") is False:
            err = (sd.get("raw") or {}).get("error") or "unreachable"
            print(f"FATAL: could not reach {url} ({err}) - nothing to "
                  "report. Check the URL/network and retry.")
            return 2
    except Exception:
        pass

    lh_ok = False
    if not args.no_lighthouse and not args.no_chrome:
        lhc = [py, str(HERE / "lighthouse.py"), url, "--out", str(lh)]
        if args.quick:
            lhc += ["--runs", "1", "--form-factors", "mobile"]
        step("Lighthouse (Core Web Vitals)", lhc)
        try:
            lh_ok = json.loads(lh.read_text()).get("available", False)
        except Exception:
            lh_ok = False

    chk = [py, str(HERE / "checks.py"), str(snap), "--out", str(findings)]
    if lh_ok:
        chk += ["--lh", str(lh)]
    if step("evaluate findings", chk) != 0:
        print("FATAL: checks step failed.")
        return 2

    step("render report", [py, str(HERE / "report.py"), str(findings),
                           "--out", str(report)])

    try:
        data = json.loads(findings.read_text())
        s = data["summary"]
        print(f"\nfidelity={data['fidelity']}  "
              f"FAIL={s['FAIL']} WARN={s['WARN']} PASS={s['PASS']} "
              f"MANUAL={s['MANUAL']} SKIPPED={s['SKIPPED']}")
    except Exception:
        pass

    # Stable machine-readable lines for the command + eval to parse.
    print(f"REPORT: {report}")
    print(f"FINDINGS: {findings}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
