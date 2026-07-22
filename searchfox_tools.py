#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  gorillanobakaa
# Free software under the GNU AGPL v3+. Use/fork/modify freely; if you distribute or run
# a modified version as a service, keep it open under the same license. Upstream:
# https://github.com/gorillanobakaa-dot/searchfox-tools
# VERSION: 2.0.0 | UPDATED: 2026-07-22 | STATUS: live
# CHANGELOG:
#   2.0.0 (2026-07-22) — RESURRECTED + IMPROVED. The original searchfox_tools.py died with
#       FIrefox.153.Work (an agent deleted the tree). Reconstructed from the brain's preserved
#       1057-line `searchfox_agent_reference.xml` + the 7-function inventory in
#       `SearchFox_Agent.xml`. Improvements over the lost original:
#         · ZERO dependencies (stdlib urllib) — never breaks on a missing `requests`.
#         · On-disk response CACHE (keyed by URL) + TTL — repeat queries don't re-hit Searchfox.
#         · Polite RATE-LIMIT + retry/backoff + real User-Agent — we borrow Mozilla's compute,
#           so we behave.
#         · `is_linux_path` NOISE FILTER on by default (the reference's Linux-only mandate);
#           `--all-platforms` to disable.
#         · `firefox-main` canonical (not the old mozilla-central).
#         · Proper CLI (search/file/symbol/includers/deps/blast-radius/map/svg-keeplist).
#   1.x — original (lost): Claude-API-integrated; searchfox_search/get_file/find_includers/
#         find_dependencies/blast_radius/symbol_info/map_relationships; is_linux_path pruning.
"""
searchfox_tools — Firefox source intelligence via Mozilla's Searchfox index.

WHY: Searchfox (searchfox.org) has ALL ~30M lines of Firefox semantically indexed on
Mozilla's servers. This offloads the heavy mapping onto THEIR compute instead of grinding
it locally (built for a machine where local grep over the tree is expensive). You query;
they compute; you get JSON back.

Usage:
    searchfox_tools.py search "AudioStream" --path dom/media
    searchfox_tools.py symbol AudioStream
    searchfox_tools.py includers AudioStream.h
    searchfox_tools.py blast-radius AudioStream      # the impact map — all files touched
    searchfox_tools.py svg-keeplist arrow-down.svg   # is this SVG referenced? (safe-to-shim check)
    searchfox_tools.py file dom/media/AudioStream.cpp

All queries default to Linux/GTK-relevant results (drops android/windows/cocoa/ios/bsd);
pass --all-platforms to include everything.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://searchfox.org"
DEFAULT_REPO = "firefox-main"
CACHE_DIR = Path(os.environ.get("SEARCHFOX_CACHE", Path.home() / ".cache" / "searchfox_tools"))
CACHE_TTL = 24 * 3600  # 1 day — the tree moves slowly relative to a work session
USER_AGENT = "gorilla-searchfox-tools/2.0 (+local Firefox-154 research; polite, cached)"
MIN_INTERVAL = 1.0  # seconds between live requests (politeness to searchfox.org)
_last_request = [0.0]

# Noise filter: drop other-platform code so we only see Linux/GTK + shared (the reference's mandate).
_OTHER_PLATFORM = re.compile(
    r"(?:^|/)(?:widget/(?:windows|cocoa|android|uikit)|mobile/(?:android|ios))(?:/|$)"
    r"|(?:android|windows|cocoa|macos|darwin|uikit|/ios/|winrt|win32|win64|bsd)",
    re.IGNORECASE,
)


def is_linux_path(path: str) -> bool:
    """True if the path is Linux/GTK-relevant or shared (i.e. NOT other-platform noise)."""
    return not _OTHER_PLATFORM.search(path or "")


# ---------------------------------------------------------------------------
# HTTP with cache + politeness
# ---------------------------------------------------------------------------
def _cache_path(url: str) -> Path:
    return CACHE_DIR / (hashlib.sha256(url.encode()).hexdigest()[:32] + ".json")


def _http_get(url: str, use_cache: bool = True) -> bytes:
    cp = _cache_path(url)
    if use_cache and cp.exists() and (time.time() - cp.stat().st_mtime) < CACHE_TTL:
        return cp.read_bytes()
    # politeness: throttle live requests
    wait = MIN_INTERVAL - (time.time() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/html;q=0.5",
    })
    last_err = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            _last_request[0] = time.time()
            if use_cache:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cp.write_bytes(data)
            return data
        except Exception as e:  # 429/5xx/timeouts → backoff
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"searchfox request failed after retries: {url}\n  {last_err}")


# ---------------------------------------------------------------------------
# Search (the JSON endpoint — the primary tool)
# ---------------------------------------------------------------------------
def _search_url(q: str, repo: str, path: str, case: bool, regexp: bool) -> str:
    params = {"q": q, "case": "true" if case else "false",
              "regexp": "true" if regexp else "false"}
    if path:
        params["path"] = path
    return f"{BASE}/{repo}/search?" + urllib.parse.urlencode(params)


def _extract_hits(obj, out):
    """Recursively pull {path, lines:[{lno,line}]} entries out of Searchfox's JSON
    (its structure nests by result-kind; we flatten defensively)."""
    if isinstance(obj, dict):
        if "path" in obj and "lines" in obj and isinstance(obj["lines"], list):
            p = obj["path"]
            for ln in obj["lines"]:
                if isinstance(ln, dict):
                    out.append((p, ln.get("lno") or ln.get("line_number") or 0,
                                (ln.get("line") or ln.get("text") or "").strip()))
        for v in obj.values():
            _extract_hits(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _extract_hits(v, out)


def search(term, repo=DEFAULT_REPO, path="", case=False, regexp=False,
           linux_only=True, limit=200, use_cache=True):
    """Run a Searchfox search; return [(path, lno, line), ...]."""
    url = _search_url(term, repo, path, case, regexp)
    raw = _http_get(url, use_cache=use_cache)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError("Searchfox did not return JSON (endpoint/markup change?). "
                           f"URL: {url}")
    hits = []
    _extract_hits(data, hits)
    # de-dup, filter, cap
    seen, out = set(), []
    for p, lno, line in hits:
        if linux_only and not is_linux_path(p):
            continue
        key = (p, lno)
        if key in seen:
            continue
        seen.add(key)
        out.append((p, lno, line))
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# Higher-level functions (the 7 from the original, rebuilt on search())
# ---------------------------------------------------------------------------
def symbol_info(symbol, repo=DEFAULT_REPO, linux_only=True):
    """Semantic definitions + usages of a symbol."""
    return search(f"symbol:{symbol}", repo=repo, linux_only=linux_only)


def find_includers(header, repo=DEFAULT_REPO, linux_only=True):
    """Files that #include the given header (by basename)."""
    base = os.path.basename(header)
    return search(f're:#include.*{re.escape(base)}', repo=repo, regexp=False,
                  linux_only=linux_only)


def get_file(path, repo=DEFAULT_REPO):
    """Raw source URL for a file (fetching full HTML source is avoided; use the URL/browser
    or `search --path` for line-level content)."""
    return f"{BASE}/{repo}/source/{path}"


def find_dependencies(path, repo=DEFAULT_REPO, linux_only=True):
    """What a file references: its own #include lines (via a path-scoped include search)."""
    return search("re:#include", repo=repo, path=path, linux_only=linux_only)


def blast_radius(name, repo=DEFAULT_REPO, linux_only=True, limit=400):
    """THE impact map: every file that references `name` (symbol usages + literal text refs
    + includers if it's a header). Returns {path: hitcount} sorted by count desc."""
    hits = []
    hits += search(f"symbol:{name}", repo=repo, linux_only=linux_only, limit=limit)
    hits += search(name, repo=repo, linux_only=linux_only, limit=limit)          # text/filename
    if name.endswith((".h", ".hpp", ".hh")):
        hits += find_includers(name, repo=repo, linux_only=linux_only)
    radius = {}
    for p, _lno, _line in hits:
        radius[p] = radius.get(p, 0) + 1
    return dict(sorted(radius.items(), key=lambda kv: (-kv[1], kv[0])))


def map_relationships(symbol, repo=DEFAULT_REPO, linux_only=True):
    """Best-effort class/relationship map: definition sites + a context view of usages."""
    defs = search(f"symbol:{symbol}", repo=repo, linux_only=linux_only, limit=50)
    ctx = search(f"context:3 re:{re.escape(symbol)}", repo=repo, linux_only=linux_only, limit=50)
    return {"definitions": defs, "context": ctx}


def svg_keeplist(svg_name, repo=DEFAULT_REPO):
    """The original mission: is this SVG referenced anywhere (CSS/markup/JS/C++)? If yes → KEEP
    (do NOT shim). Returns (verdict, referencing_files). Uses Mozilla's index, not local grep."""
    base = os.path.basename(svg_name)
    hits = search(base, repo=repo, linux_only=False, limit=300)  # SVGs are cross-platform assets
    files = sorted({p for p, _l, _ln in hits})
    verdict = "KEEP (referenced — do NOT shim)" if files else "SAFE TO SHIM (no references found)"
    return verdict, files


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _print_hits(hits):
    for p, lno, line in hits:
        print(f"  {p}:{lno}: {line[:140]}")
    print(f"  — {len(hits)} hit(s)", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(prog="searchfox", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=DEFAULT_REPO, help=f"searchfox repo (default {DEFAULT_REPO})")
    ap.add_argument("--all-platforms", action="store_true", help="disable the Linux-only noise filter")
    ap.add_argument("--no-cache", action="store_true", help="bypass the on-disk cache")
    sub = ap.add_subparsers(dest="cmd")

    s = sub.add_parser("search", help="raw search")
    s.add_argument("query"); s.add_argument("--path", default=""); s.add_argument("--case", action="store_true")
    s.add_argument("--regexp", action="store_true")
    sub.add_parser("symbol", help="symbol definitions + usages").add_argument("name")
    sub.add_parser("includers", help="files that #include a header").add_argument("header")
    sub.add_parser("deps", help="a file's #include dependencies").add_argument("path")
    sub.add_parser("blast-radius", help="every file referencing a name (impact map)").add_argument("name")
    sub.add_parser("map", help="class/relationship map").add_argument("symbol")
    sub.add_parser("file", help="raw source URL for a path").add_argument("path")
    sub.add_parser("svg-keeplist", help="is an SVG referenced? (safe-to-shim check)").add_argument("svg")

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help(); return 0
    lin = not args.all_platforms
    uc = not args.no_cache

    try:
        if args.cmd == "search":
            _print_hits(search(args.query, args.repo, args.path, args.case, args.regexp, lin, use_cache=uc))
        elif args.cmd == "symbol":
            _print_hits(symbol_info(args.name, args.repo, lin))
        elif args.cmd == "includers":
            _print_hits(find_includers(args.header, args.repo, lin))
        elif args.cmd == "deps":
            _print_hits(find_dependencies(args.path, args.repo, lin))
        elif args.cmd == "blast-radius":
            radius = blast_radius(args.name, args.repo, lin)
            for p, n in radius.items():
                print(f"  {n:3}x  {p}")
            print(f"  — blast radius: {len(radius)} file(s) reference '{args.name}'", file=sys.stderr)
        elif args.cmd == "map":
            r = map_relationships(args.symbol, args.repo, lin)
            print("definitions:"); _print_hits(r["definitions"])
            print("context:"); _print_hits(r["context"])
        elif args.cmd == "file":
            print(get_file(args.path, args.repo))
        elif args.cmd == "svg-keeplist":
            verdict, files = svg_keeplist(args.svg, args.repo)
            print(f"  VERDICT: {verdict}")
            for f in files:
                print(f"    · {f}")
    except Exception as e:
        print(f"searchfox: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
