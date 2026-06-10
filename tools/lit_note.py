#!/usr/bin/env python3
"""Bridge Zotero -> Obsidian: generate/refresh literature notes and topic MOCs.

Each paper becomes Literature/<slug>.md. The note has two regions:

  * Everything ABOVE the marker line is MANAGED: regenerated from Zotero on every
    sync (frontmatter, metadata, abstract, your highlights, your Zotero notes).
  * Everything BELOW the marker is YOURS: your synthesis, connections, [[links]].
    Sync never touches it.

Topic MOCs (Topics/<collection>.md) link to every member paper and are also
split the same way, so your hand-written framing survives re-generation.

Usage:
    lit_note.py sync KEY [KEY ...]
    lit_note.py sync-all [--collection NAME] [--since YYYY-MM-DD]
    lit_note.py topics
    lit_note.py path KEY          # print the note path for a Zotero key
"""
import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIT = os.path.join(ROOT, "Literature")
TOPICS = os.path.join(ROOT, "Topics")
READER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zotero_read.py")

MARKER = "<!-- ===== Below this line is yours; sync never touches it ===== -->"


def reader(*args):
    out = subprocess.check_output([sys.executable, READER, *args], text=True)
    return json.loads(out) if out.strip() else None


def slugify(s, maxlen=80):
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    s = re.sub(r"[\s_-]+", "-", s)
    return s[:maxlen].strip("-") or "untitled"


def note_filename(item):
    first = (item["authors"][0].split()[-1] if item["authors"] else "anon").lower()
    first = re.sub(r"[^\w]", "", first)
    year = item.get("year") or "nd"
    title_words = slugify(item["title"], 50)
    return f"{first}{year}-{title_words}.md"


def find_existing(zotero_key):
    """Locate an existing note for this key (filename may have been edited)."""
    if not os.path.isdir(LIT):
        return None
    for fn in os.listdir(LIT):
        if not fn.endswith(".md"):
            continue
        p = os.path.join(LIT, fn)
        with open(p, encoding="utf-8") as f:
            head = f.read(600)
        if re.search(rf"^zotero_key:\s*{re.escape(zotero_key)}\s*$", head, re.M):
            return p
    return None


def split_note(text):
    """Return (managed, yours) where yours includes the marker line."""
    if MARKER in text:
        i = text.index(MARKER)
        return text[:i], text[i:]
    return text, None


def yaml_list(xs):
    return "[" + ", ".join(json.dumps(x, ensure_ascii=False) for x in xs) + "]"


def build_managed(item):
    L = []
    L.append("---")
    L.append(f"zotero_key: {item['key']}")
    L.append(f"title: {json.dumps(item['title'], ensure_ascii=False)}")
    L.append(f"authors: {yaml_list(item['authors'])}")
    if item.get("year"):
        L.append(f"year: {item['year']}")
    if item.get("arxiv"):
        L.append(f"arxiv: {item['arxiv']}")
    if item.get("DOI"):
        L.append(f"doi: {item['DOI']}")
    L.append(f"collections: {yaml_list(item['collections'])}")
    L.append(f"tags: {yaml_list(['paper'] + item['tags'])}")
    L.append("status: unread")
    L.append(f"zotero_added: {item.get('dateAdded','')}")
    L.append("---")
    L.append("")
    L.append(f"# {item['title']}")
    L.append("")
    authors = ", ".join(item["authors"]) or "—"
    L.append(f"**Authors:** {authors}  ")
    venue = item.get("publication") or ""
    line = f"**Year:** {item.get('year','?')}"
    if venue:
        line += f" · {venue}"
    if item.get("arxiv"):
        line += f" · [arXiv:{item['arxiv']}](https://arxiv.org/abs/{item['arxiv']})"
    elif item.get("url"):
        line += f" · [link]({item['url']})"
    L.append(line + "  ")
    if item["collections"]:
        L.append("**Topics:** " + ", ".join(f"[[{c}]]" for c in item["collections"]) + "  ")
    pdfs = [a["path"] for a in item.get("attachments", [])
            if a.get("contentType") == "application/pdf" and a.get("path")]
    if pdfs:
        L.append(f"**PDF:** [open]({'file://' + pdfs[0].replace(' ', '%20')})  ")
    L.append("")
    if item.get("abstract"):
        L.append("## Abstract")
        L.append("")
        L.append(item["abstract"].strip())
        L.append("")
    anns = item.get("annotations", [])
    if anns:
        L.append(f"## My Highlights ({len(anns)})")
        L.append("*From Zotero — these are what you flagged as important.*")
        L.append("")
        for a in anns:
            text = (a.get("text") or "").strip().replace("\n", " ")
            page = a.get("page") or "?"
            if text:
                L.append(f"> [!quote] p{page}")
                L.append(f"> {text}")
            if a.get("comment"):
                L.append(f">")
                L.append(f"> 💬 {a['comment'].strip()}")
            L.append("")
    notes = item.get("notes", [])
    if notes:
        L.append("## My Zotero Notes")
        L.append("")
        for n in notes:
            L.append(n.strip())
            L.append("")
    L.append("")
    return "\n".join(L)


def default_yours():
    return (
        MARKER + "\n\n"
        "## 核心思想\n"
        "（一两句话：这篇到底做了什么、解决了什么问题）\n\n"
        "## 为什么重要 / 我能借鉴\n\n"
        "## 和哪些论文相关\n"
        "- [[在这里关联其他论文]]\n\n"
        "## 疑问 / TODO\n"
        "- \n"
    )


def sync_one(key):
    item = reader("item", key)
    managed = build_managed(item)
    existing = find_existing(key)
    if existing:
        with open(existing, encoding="utf-8") as f:
            _, yours = split_note(f.read())
        if yours is None:
            yours = default_yours()
        path = existing
    else:
        yours = default_yours()
        path = os.path.join(LIT, note_filename(item))
    os.makedirs(LIT, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(managed + yours)
    return path, bool(existing)


def cmd_sync(args):
    for key in args.keys:
        path, updated = sync_one(key)
        print(f"{'updated' if updated else 'created'}  {os.path.relpath(path, ROOT)}")


def cmd_sync_all(args):
    listargs = ["list"]
    if args.collection:
        listargs += ["--collection", args.collection]
    if args.since:
        listargs += ["--since", args.since]
    items = reader(*listargs)
    n = 0
    for it in items:
        path, updated = sync_one(it["key"])
        n += 1
        print(f"[{n}/{len(items)}] {'upd' if updated else 'new'}  {os.path.basename(path)}")
    print(f"\nsynced {n} notes into Literature/")


def cmd_topics(args):
    cols = reader("collections")
    items = reader("list")
    os.makedirs(TOPICS, exist_ok=True)
    by_col = {}
    for it in items:
        for c in it["collections"]:
            by_col.setdefault(c, []).append(it)
    for col in cols:
        name = col["name"]
        members = sorted(by_col.get(name, []), key=lambda x: x.get("year", ""), reverse=True)
        path = os.path.join(TOPICS, f"{name}.md")
        yours = None
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                _, yours = split_note(f.read())
        if yours is None:
            yours = (MARKER + "\n\n## Overview\n*What this area is about, key threads, open problems.*\n\n## Map\n- \n")
        L = ["---", f"title: {name}", "tags: [topic, MOC]", "---", "",
             f"# {name}", "", f"*{len(members)} papers.* Auto-listed below; your map is at the bottom.", ""]
        L.append("## Papers")
        for it in members:
            fn = note_filename(it)[:-3]
            yr = it.get("year", "")
            ann = it.get("nAnnotations", 0)
            flag = f" · {ann}🔖" if ann else ""
            L.append(f"- [[{fn}|{it['title']}]] ({yr}){flag}")
        L.append("")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(L) + yours)
        print(f"topic  {name}.md  ({len(members)} papers)")


def cmd_path(args):
    item = reader("item", args.key)
    existing = find_existing(args.key)
    print(existing or os.path.join(LIT, note_filename(item)))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync"); s.add_argument("keys", nargs="+")
    sa = sub.add_parser("sync-all"); sa.add_argument("--collection"); sa.add_argument("--since")
    sub.add_parser("topics")
    pp = sub.add_parser("path"); pp.add_argument("key")
    args = p.parse_args()
    {"sync": cmd_sync, "sync-all": cmd_sync_all, "topics": cmd_topics, "path": cmd_path}[args.cmd](args)


if __name__ == "__main__":
    main()
