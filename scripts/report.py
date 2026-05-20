#!/usr/bin/env python3
"""
report.py - findings.json -> report.html

Single self-contained HTML file: inline CSS, no external assets, no JS
required. To-the-point: a verdict line, a status summary, and findings
grouped by section with the exact copy-paste fix.

Python 3 stdlib only.
"""

import argparse
import html
import json
import sys
from collections import OrderedDict

BADGE = {
    "PASS": ("#136f3b", "#e6f4ea", "PASS"),
    "WARN": ("#8a5a00", "#fdf3df", "WARN"),
    "FAIL": ("#b3261e", "#fce8e6", "FAIL"),
    "SKIPPED": ("#5f6368", "#eceff1", "SKIPPED"),
    "MANUAL": ("#1a56b8", "#e8f0fe", "MANUAL"),
}

CSS = """
*{box-sizing:border-box}
body{font:15px/1.55 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
 color:#202124;margin:0;background:#f6f7f9}
.wrap{max-width:920px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:22px;margin:0 0 4px} h2{font-size:18px;margin:34px 0 12px;
 border-bottom:1px solid #e0e0e0;padding-bottom:6px}
.muted{color:#5f6368;font-size:13px}
.head{background:#fff;border:1px solid #e0e0e0;border-radius:10px;
 padding:18px 20px;margin-bottom:18px}
.chips{margin-top:12px;display:flex;flex-wrap:wrap;gap:8px}
.chip{font-size:12px;font-weight:600;padding:5px 10px;border-radius:999px}
.verdict{font-size:15px;font-weight:600;margin-top:12px}
.fid{display:inline-block;font-size:12px;font-weight:600;padding:3px 9px;
 border-radius:6px;margin-left:8px}
.fid.full{background:#e6f4ea;color:#136f3b}
.fid.degraded{background:#fdf3df;color:#8a5a00}
.item{background:#fff;border:1px solid #e0e0e0;border-radius:10px;
 padding:14px 16px;margin:10px 0}
.item .top{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.badge{font-size:11px;font-weight:700;padding:3px 8px;border-radius:5px}
.name{font-weight:600} .ev{margin:8px 0 0;font-size:14px}
.ref{color:#5f6368;font-size:12px;margin-top:4px}
pre{background:#0d1117;color:#e6edf3;padding:12px 14px;border-radius:8px;
 overflow:auto;font-size:12.5px;margin:10px 0 0;white-space:pre-wrap}
"""


def chip(label, fg, bg, n):
    return (f'<span class="chip" style="color:{fg};background:{bg}">'
            f'{label} {n}</span>')


def render(data):
    s = data["summary"]
    url = html.escape(data.get("url") or "")
    fid = data.get("fidelity", "degraded")
    fail, warn = s.get("FAIL", 0), s.get("WARN", 0)
    if fail == 0 and warn == 0:
        verdict = "No blocking issues found. Address any MANUAL setup items."
    elif fail:
        verdict = (f"{fail} critical issue(s) and {warn} warning(s) to fix - "
                   "these are likely why the site is hard to find.")
    else:
        verdict = f"No critical failures, {warn} warning(s) worth fixing."

    fid_note = ("Full fidelity (Chrome render + Lighthouse)." if fid == "full"
                else "Degraded run - some checks limited (no Chrome/Lighthouse "
                "on this surface). Re-run on Claude Code / Desktop Local for "
                "Core Web Vitals.")

    parts = []
    parts.append('<div class="head">')
    parts.append(f"<h1>SEO Visibility Report</h1>")
    parts.append(f'<div class="muted">{url} &middot; '
                  f'{html.escape(str(data.get("fetched_at") or ""))} &middot; '
                  f'render: {html.escape(data.get("render_mode") or "?")}'
                  f'<span class="fid {fid}">{fid.upper()}</span></div>')
    parts.append(f'<div class="verdict">{html.escape(verdict)}</div>')
    parts.append(f'<div class="muted" style="margin-top:6px">{fid_note}</div>')
    parts.append('<div class="chips">')
    for k in ("FAIL", "WARN", "PASS", "MANUAL", "SKIPPED"):
        fg, bg, lbl = BADGE[k]
        parts.append(chip(lbl, fg, bg, s.get(k, 0)))
    parts.append("</div></div>")

    groups = OrderedDict()
    for fnd in data["findings"]:
        groups.setdefault(fnd["part"], []).append(fnd)

    for part, items in groups.items():
        parts.append(f"<h2>{html.escape(part)}</h2>")
        for it in items:
            fg, bg, lbl = BADGE.get(it["status"], BADGE["SKIPPED"])
            parts.append('<div class="item"><div class="top">')
            parts.append(f'<span class="badge" style="color:{fg};'
                         f'background:{bg}">{lbl}</span>')
            parts.append(f'<span class="name">{html.escape(it["check"])}</span>'
                         '</div>')
            parts.append(f'<div class="ev">{html.escape(it["evidence"])}</div>')
            fix = (it.get("fix") or "").strip()
            if fix and fix != "-":
                parts.append(f"<pre>{html.escape(fix)}</pre>")
            parts.append(f'<div class="ref">{html.escape(it.get("ref",""))}'
                         "</div>")
            parts.append("</div>")

    return (f"<!doctype html><html lang=en><head><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width,"
            f"initial-scale=1'><title>SEO Visibility Report - {url}</title>"
            f"<style>{CSS}</style></head><body><div class=wrap>"
            f"{''.join(parts)}"
            f"<p class='muted' style='margin-top:40px'>Generated by the SEO "
            f"Visibility plugin.</p></div></body></html>")


def main(argv=None):
    ap = argparse.ArgumentParser(description="findings.json -> report.html")
    ap.add_argument("findings")
    ap.add_argument("--out", default="report.html")
    args = ap.parse_args(argv)

    with open(args.findings, encoding="utf-8") as fh:
        data = json.load(fh)
    htmlstr = render(data)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(htmlstr)
    print(f"report -> {args.out}  ({len(data['findings'])} findings, "
          f"fidelity={data.get('fidelity')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
