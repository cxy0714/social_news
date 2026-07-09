#!/usr/bin/env python3
"""Read the private watchlist Gist and emit a PUBLIC read-only snapshot.

The browser client stores your future-tech watchlist in ONE private Gist
(file ``watchlist.json``). That Gist is only visible to you. To let logged-out
visitors see the collection, a scheduled GitHub Action runs this script with a
repo secret ``GIST_TOKEN`` (a PAT with the ``gist`` scope), reads that Gist, and
writes ``web/data/watchlist_public.json`` — which build.py inlines into the site.

Only the fields safe to publish are exported (title / url / source / category /
note / added). No token ever touches the repo; it lives only in the Action env.

Env:
    GIST_TOKEN   required — PAT with `gist` scope (repo secret)
    SN_GIST_ID   optional — pin the Gist id; otherwise discovered by filename/desc

Usage:
    GIST_TOKEN=... python scripts/publish_watchlist.py
    python scripts/publish_watchlist.py --out web/data/watchlist_public.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "web" / "data" / "watchlist_public.json"

WL_FILE = "watchlist.json"
# Must match the description the browser client uses when it auto-creates the Gist.
GIST_DESC = "social_news · 未来技术待调研 watchlist（请勿删除）"
API = "https://api.github.com"

# Fields exported to the public snapshot (never publish the token or raw Gist).
PUB_FIELDS = ("title", "url", "source", "source_url", "category", "note", "added")


def _get(url: str, token: str) -> object:
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "User-Agent": "social_news-publish-watchlist",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def find_gist_id(token: str) -> str | None:
    """Pinned SN_GIST_ID wins; else scan the account for the watchlist Gist."""
    pinned = (os.environ.get("SN_GIST_ID") or "").strip()
    if pinned:
        return pinned
    try:
        gists = _get(API + "/gists?per_page=100", token)
    except urllib.error.URLError as e:  # network / auth failure
        print(f"warn: listing gists failed: {e}", file=sys.stderr)
        return None
    for g in gists if isinstance(gists, list) else []:
        files = g.get("files") or {}
        if g.get("description") == GIST_DESC or WL_FILE in files:
            return g.get("id")
    return None


def fetch_watchlist(token: str, gist_id: str) -> list[dict]:
    g = _get(API + "/gists/" + gist_id, token)
    files = g.get("files") or {}
    f = files.get(WL_FILE) or {}
    content = f.get("content")
    # Large gist files are truncated inline; fall back to raw_url.
    if f.get("truncated") and f.get("raw_url"):
        with urllib.request.urlopen(f["raw_url"], timeout=30) as r:
            content = r.read().decode("utf-8")
    if not content:
        return []
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []
    # Accept both the array shape and a {url: item} map.
    if isinstance(data, dict):
        data = list(data.values())
    return data if isinstance(data, list) else []


def build_public(items: list[dict]) -> list[dict]:
    out = []
    for it in items:
        if not isinstance(it, dict) or not it.get("url"):
            continue
        out.append({k: it[k] for k in PUB_FIELDS if it.get(k)})
    out.sort(key=lambda x: x.get("added", ""), reverse=True)
    return out


def write_snapshot(out_path: Path, items: list[dict]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(out_path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="snapshot output path")
    args = ap.parse_args()
    out_path = Path(args.out)

    token = (os.environ.get("GIST_TOKEN") or "").strip()
    if not token:
        # No secret configured: emit an empty snapshot so the build still works.
        print("no GIST_TOKEN — writing empty snapshot", file=sys.stderr)
        write_snapshot(out_path, [])
        return 0

    gist_id = find_gist_id(token)
    if not gist_id:
        print("no watchlist gist found — writing empty snapshot", file=sys.stderr)
        write_snapshot(out_path, [])
        return 0

    try:
        raw = fetch_watchlist(token, gist_id)
    except urllib.error.URLError as e:
        print(f"warn: reading gist failed: {e}", file=sys.stderr)
        write_snapshot(out_path, [])
        return 0

    pub = build_public(raw)
    write_snapshot(out_path, pub)
    print(f"wrote {len(pub)} public watchlist items -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
