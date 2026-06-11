#!/usr/bin/env python3
"""Resurface kept-but-unread papers ("积压重浮").

Lists Zotero items that were added more than N days ago but still have ZERO
highlights and ZERO notes — i.e. saved but never actually engaged with. Run
weekly (weekly.sh) so "collected" doesn't silently masquerade as "read".

Stdlib only; Zotero is read via zotero_read.py (read-only).

Usage:
    backlog.py [--days 14] [--limit 15] [--json]
"""
import argparse
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paperlib as P

LIT = os.path.join(P.ROOT, "Literature")


def note_map():
    """zotero_key -> note filename (sans .md), scanning Literature/ frontmatter."""
    out = {}
    if not os.path.isdir(LIT):
        return out
    for fn in os.listdir(LIT):
        if not fn.endswith(".md"):
            continue
        try:
            with open(os.path.join(LIT, fn), encoding="utf-8") as f:
                head = f.read(600)
        except OSError:
            continue
        m = re.search(r"^zotero_key:\s*(\S+)\s*$", head, re.M)
        if m:
            out[m.group(1)] = fn[:-3]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=14,
                    help="grace period before an untouched paper counts as backlog")
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    items = P.reader("list")
    notes = note_map()
    today = dt.date.today()
    cutoff = (today - dt.timedelta(days=args.days)).isoformat()

    stale = []
    for it in items:
        added = (it.get("dateAdded") or "")[:10]
        if not added or added > cutoff:
            continue
        if it.get("nAnnotations", 0) or it.get("nNotes", 0):
            continue
        it["_age"] = (today - dt.date.fromisoformat(added)).days
        stale.append(it)
    stale.sort(key=lambda x: -x["_age"])           # oldest debt first
    shown = stale[:args.limit]

    if args.json:
        print(json.dumps([{
            "key": it["key"], "title": it["title"], "age_days": it["_age"],
            "collections": it.get("collections", []), "arxiv": it.get("arxiv"),
            "note": notes.get(it["key"]),
        } for it in shown], ensure_ascii=False, indent=2))
        return

    if not stale:
        print(f"积压为零 — 库里没有入库超过 {args.days} 天且零高亮零笔记的论文 🎉")
        return

    print(f"**📚 积压重浮** — {len(stale)} 篇入库 >{args.days} 天但还没有任何高亮/笔记"
          f"（显示最久的 {len(shown)} 篇）。读一篇、或者承认不会读就移出去：\n")
    for it in shown:
        link = f"[[{notes[it['key']]}|{it['title']}]]" if it["key"] in notes else it["title"]
        cols = "/".join(it.get("collections", [])) or "—"
        print(f"- {link} — {cols} · 入库 {it['_age']} 天 · `{it['key']}`")


if __name__ == "__main__":
    main()
