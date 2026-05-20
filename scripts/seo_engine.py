#!/usr/bin/env python3
"""
seo_engine.py - run-once crawler for the SEO Visibility plugin.

Fetches a URL once and captures everything the topic checkers need, so the
audit never refetches: raw HTML, Chrome-rendered DOM (when Chrome is present),
response headers/timing, robots.txt, and discovered sitemaps. Output is a
single snapshot.json that checks.py consumes.

Python 3 stdlib only. No third-party packages. No hardcoded interpreter path.
Chrome is optional: when absent, the snapshot still carries the raw fetch and
flags that JS-rendered checks are limited (graceful degradation for hosted
sandbox surfaces).
"""

import argparse
import gzip
import io
import json
import os
import platform
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

UA = (
    "Mozilla/5.0 (compatible; SEOVisibilityBot/1.0; "
    "+https://github.com/seo-audit-plugin) Chrome/126 Safari/537.36"
)
MAX_HTML_BYTES = 3_000_000      # cap stored HTML so snapshot.json stays sane
MAX_SITEMAP_BYTES = 12_000_000  # read budget per sitemap file
MAX_SITEMAPS = 5                # don't chase an unbounded sitemap index


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def normalize_url(raw):
    raw = raw.strip()
    if not urlparse(raw).scheme:
        raw = "https://" + raw
    return raw


def origin_of(url):
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def http_get(url, timeout, accept="*/*"):
    """GET with a real UA. Returns dict; never raises."""
    out = {
        "url": url, "status": None, "ok": False, "final_url": url,
        "headers": {}, "elapsed_ms": None, "bytes": 0, "body": "",
        "tls_ok": True, "error": None,
    }
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    start = time.time()

    def _read(resp):
        out["status"] = getattr(resp, "status", resp.getcode())
        out["final_url"] = resp.geturl()
        out["headers"] = {k.lower(): v for k, v in resp.headers.items()}
        data = resp.read(MAX_HTML_BYTES + 1)
        if data[:2] == b"\x1f\x8b":  # gzip magic, server ignored our identity hint
            try:
                data = gzip.decompress(data)
            except OSError:
                pass
        out["bytes"] = len(data)
        charset = "utf-8"
        ctype = out["headers"].get("content-type", "")
        if "charset=" in ctype:
            charset = ctype.split("charset=")[-1].split(";")[0].strip() or "utf-8"
        out["body"] = data[:MAX_HTML_BYTES].decode(charset, errors="replace")
        out["ok"] = 200 <= (out["status"] or 0) < 400

    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            _read(resp)
    except urllib.error.HTTPError as e:
        out["status"] = e.code
        out["final_url"] = e.url if hasattr(e, "url") else url
        try:
            out["headers"] = {k.lower(): v for k, v in e.headers.items()}
            out["body"] = e.read(MAX_HTML_BYTES).decode("utf-8", errors="replace")
        except Exception:
            pass
        out["error"] = f"HTTP {e.code}"
    except ssl.SSLError as e:
        out["tls_ok"] = False
        try:  # still fetch so we can audit; record the TLS problem
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                _read(resp)
            out["error"] = f"TLS verification failed: {e}"
        except Exception as e2:
            out["error"] = f"TLS error: {e2}"
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"

    out["elapsed_ms"] = int((time.time() - start) * 1000)
    return out


def find_chrome(explicit=None):
    if explicit:
        return explicit if os.path.exists(explicit) else None
    env = os.environ.get("CHROME_PATH")
    if env and os.path.exists(env):
        return env
    sysname = platform.system()
    candidates = []
    if sysname == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
    elif sysname == "Windows":
        pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        pf86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            os.path.join(pf, r"Google\Chrome\Application\chrome.exe"),
            os.path.join(pf86, r"Google\Chrome\Application\chrome.exe"),
            os.path.join(local, r"Google\Chrome\Application\chrome.exe"),
            os.path.join(pf, r"Microsoft\Edge\Application\msedge.exe"),
        ]
    else:  # Linux / other
        for name in ("google-chrome", "google-chrome-stable", "chromium",
                     "chromium-browser", "chrome"):
            p = shutil.which(name)
            if p:
                candidates.append(p)
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def chrome_version(path):
    try:
        r = subprocess.run([path, "--version"], capture_output=True,
                           text=True, timeout=15)
        return (r.stdout or r.stderr).strip() or None
    except Exception:
        return None


def render_with_chrome(path, url, timeout):
    """Return rendered DOM HTML via headless Chrome, or (None, error)."""
    base = [
        path, "--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage",
        "--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
        "--virtual-time-budget=9000", "--timeout=15000", "--dump-dom", url,
    ]
    for headless in ("--headless=new", "--headless"):
        try:
            r = subprocess.run([base[0], headless] + base[1:],
                               capture_output=True, text=True, timeout=timeout)
            dom = r.stdout or ""
            if len(dom) > 200:
                return dom[:MAX_HTML_BYTES], None
            if headless == "--headless":
                return None, (r.stderr or "empty DOM").strip()[:500]
        except subprocess.TimeoutExpired:
            if headless == "--headless":
                return None, "chrome render timed out"
        except Exception as e:
            if headless == "--headless":
                return None, f"{type(e).__name__}: {e}"
    return None, "chrome render produced no DOM"


def parse_sitemap(body_bytes):
    """Return (kind, entry_count, valid_xml). Streams to bound memory."""
    try:
        kind, count = None, 0
        for event, elem in ET.iterparse(io.BytesIO(body_bytes), events=("end",)):
            tag = elem.tag.split("}")[-1].lower()
            if tag == "url":
                kind = kind or "urlset"
                count += 1
            elif tag == "sitemap":
                kind = kind or "sitemapindex"
                count += 1
            if tag in ("url", "sitemap"):
                elem.clear()
        return kind, count, True
    except ET.ParseError:
        return None, 0, False
    except Exception:
        return None, 0, False


def fetch_sitemap(url, timeout):
    rec = {"url": url, "status": None, "ok": False, "bytes": 0,
           "valid_xml": False, "kind": None, "entry_count": 0, "error": None}
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            rec["status"] = getattr(resp, "status", resp.getcode())
            data = resp.read(MAX_SITEMAP_BYTES)
            if url.endswith(".gz") or data[:2] == b"\x1f\x8b":
                try:
                    data = gzip.decompress(data)
                except OSError:
                    pass
            rec["bytes"] = len(data)
            rec["ok"] = 200 <= (rec["status"] or 0) < 400
            if rec["ok"]:
                rec["kind"], rec["entry_count"], rec["valid_xml"] = parse_sitemap(data)
    except urllib.error.HTTPError as e:
        rec["status"], rec["error"] = e.code, f"HTTP {e.code}"
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}"
    return rec


def parse_robots_sitemaps(body):
    lines = []
    for ln in body.splitlines():
        s = ln.strip()
        if s.lower().startswith("sitemap:"):
            val = s.split(":", 1)[1].strip()
            if val:
                lines.append(val)
    return lines


def build_snapshot(url, timeout, no_chrome, chrome_path_arg):
    warnings = []
    input_url = normalize_url(url)

    raw = http_get(input_url, timeout, accept="text/html,application/xhtml+xml,*/*")
    final_url = raw.get("final_url") or input_url
    origin = origin_of(final_url)
    if raw["error"]:
        warnings.append(f"raw fetch: {raw['error']}")

    # A None status means the server never responded (DNS / refused / timeout)
    # - the site is unreachable. A 4xx/5xx still counts as reachable (we report
    # the error page). When unreachable, skip Chrome: it only yields its own
    # "site can't be reached" interstitial, which would mask the failure.
    reachable = bool(raw["ok"] or raw["status"])

    chrome_path = (None if (no_chrome or not reachable)
                   else find_chrome(chrome_path_arg))
    rendered = {"engine": None, "html": None, "error": None}
    if chrome_path:
        dom, err = render_with_chrome(chrome_path, final_url, timeout + 15)
        if dom:
            rendered = {"engine": "chrome", "html": dom, "error": None}
        else:
            rendered["error"] = err
            warnings.append(f"chrome render: {err}; using raw HTML")
    else:
        warnings.append(
            "Chrome not found - JS-rendered checks limited; using raw HTML "
            "(set CHROME_PATH or install Chrome for full fidelity)"
        )

    robots_url = urljoin(origin + "/", "robots.txt")
    rg = http_get(robots_url, timeout, accept="text/plain,*/*")
    sitemap_lines = parse_robots_sitemaps(rg["body"]) if rg["ok"] else []
    robots = {
        "url": robots_url, "status": rg["status"], "ok": rg["ok"],
        "body": rg["body"][:200_000], "sitemap_lines": sitemap_lines,
        "error": rg["error"],
    }

    candidates, seen = [], set()
    for s in sitemap_lines + [urljoin(origin + "/", "sitemap.xml")]:
        if s not in seen:
            seen.add(s)
            candidates.append(s)
    sitemaps = [fetch_sitemap(s, timeout) for s in candidates[:MAX_SITEMAPS]]

    return {
        "schema": 1,
        "tool": "seo_engine.py",
        "input_url": input_url,
        "final_url": final_url,
        "origin": origin,
        "reachable": reachable,
        "fetched_at": now_iso(),
        "raw": {
            "status": raw["status"], "ok": raw["ok"],
            "headers": raw["headers"], "elapsed_ms": raw["elapsed_ms"],
            "bytes": raw["bytes"], "tls_ok": raw["tls_ok"],
            "html": raw["body"], "error": raw["error"],
        },
        "rendered": rendered,
        "chrome": {
            "available": bool(chrome_path),
            "path": chrome_path,
            "version": chrome_version(chrome_path) if chrome_path else None,
        },
        "robots": robots,
        "sitemaps": sitemaps,
        "warnings": warnings,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run-once crawler -> snapshot.json")
    ap.add_argument("url", help="site URL to audit")
    ap.add_argument("--out", default="snapshot.json", help="output path")
    ap.add_argument("--timeout", type=int, default=20, help="per-request seconds")
    ap.add_argument("--no-chrome", action="store_true",
                    help="force raw fetch only (skip Chrome render)")
    ap.add_argument("--chrome-path", default=None, help="explicit Chrome binary")
    args = ap.parse_args(argv)

    snap = build_snapshot(args.url, args.timeout, args.no_chrome,
                          args.chrome_path)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)

    eng = snap["rendered"]["engine"] or "raw-only"
    rs = snap["raw"]["status"]
    print(f"snapshot -> {args.out}  (status={rs}, render={eng}, "
          f"sitemaps={len(snap['sitemaps'])}, warnings={len(snap['warnings'])})")
    return 0 if (snap["raw"]["ok"] or snap["raw"]["status"]) else 1


if __name__ == "__main__":
    sys.exit(main())
