#!/usr/bin/env python3
"""Conference acceptance scan (会议放榜扫描): when a venue's accepted list is
out, sweep it, score every paper against your interest profile (same scoring
as fetch.py: learned library keywords + .interests.yaml boosts), and write a
ranked "本届必读" report to Research/conf/<venue>-<year>.md.

Sources:
  * OpenReview API v2  — iclr / neurips / corl / icml (full accepted list,
    incl. oral/spotlight flags)
  * arXiv comment search — icra / rss / cvpr / any venue: finds arXiv papers
    whose comment says "Accepted to <VENUE> <YEAR>" (partial but zero-infra;
    grows as authors update their arXiv comments)

Stdlib only.

Usage:
    confscan.py corl [2026] [--top 30] [--source openreview|arxiv]
    confscan.py icra 2026                # arXiv comment search
    confscan.py --venueid robot-learning.org/CoRL/2026/Conference  # raw override
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paperlib as P

OUTDIR = os.path.join(P.ROOT, "Research", "conf")

OPENREVIEW = {
    "iclr":    "ICLR.cc/{y}/Conference",
    "neurips": "NeurIPS.cc/{y}/Conference",
    "icml":    "ICML.cc/{y}/Conference",
    "corl":    "robot-learning.org/CoRL/{y}/Conference",
}


def openreview_accepted(venueid):
    """All accepted notes for a venueid (post-decision, accepted papers carry it)."""
    out, offset, limit = [], 0, 1000
    while True:
        url = ("https://api2.openreview.net/notes?" + urllib.parse.urlencode({
            "content.venueid": venueid, "limit": limit, "offset": offset}))
        req = urllib.request.Request(url, headers={"User-Agent": "paper-agent/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)
        except Exception as e:
            print(f"warn: openreview @{offset}: {e}", file=sys.stderr)
            break
        notes = data.get("notes", [])
        if not notes:
            break
        for n in notes:
            c = n.get("content", {})
            get = lambda k: (c.get(k) or {}).get("value") or ""
            track = get("venue")          # e.g. "NeurIPS 2025 spotlight"
            flag = ""
            for f in ("oral", "spotlight", "award"):
                if f in track.lower():
                    flag = f
            out.append({
                "title": " ".join(str(get("title")).split()),
                "abstract": " ".join(str(get("abstract")).split()),
                "authors": [a for a in (get("authors") or [])][:10]
                           if isinstance(get("authors"), list) else [],
                "url": f"https://openreview.net/forum?id={n.get('forum') or n.get('id')}",
                "published": "", "venue_hint": track, "venue": track,
                "flag": flag, "source": "openreview", "categories": [],
            })
        offset += limit
        if len(notes) < limit:
            break
        time.sleep(1)
    return out


def arxiv_comment_search(query, max_n=600):
    """arXiv papers whose comment field mentions e.g. 'ICRA 2026'."""
    out, page, start = [], 200, 0
    ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    while start < max_n:
        url = ("http://export.arxiv.org/api/query?" + urllib.parse.urlencode({
            "search_query": f'co:"{query}"', "sortBy": "submittedDate",
            "sortOrder": "descending", "start": start, "max_results": page}))
        req = urllib.request.Request(url, headers={"User-Agent": "paper-agent/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                root = ET.fromstring(r.read())
        except Exception as e:
            print(f"warn: arxiv @{start}: {e}", file=sys.stderr)
            break
        entries = root.findall("a:entry", ns)
        if not entries:
            break
        for e in entries:
            aid = e.find("a:id", ns).text
            m = re.search(r"(\d{4}\.\d{4,5})", aid)
            comment_el = e.find("arxiv:comment", ns)
            comment = comment_el.text if comment_el is not None else ""
            # require an acceptance-ish phrasing, not a mere mention
            if not re.search(r"accept|to appear|camera.ready|" + re.escape(query),
                             comment or "", re.I):
                continue
            out.append({
                "arxiv": m.group(1) if m else aid,
                "title": " ".join(e.find("a:title", ns).text.split()),
                "abstract": " ".join(e.find("a:summary", ns).text.split()),
                "authors": [a.find("a:name", ns).text for a in e.findall("a:author", ns)][:10],
                "published": e.find("a:published", ns).text[:10],
                "url": aid, "venue_hint": comment or "", "venue": query,
                "flag": "", "source": "arxiv", "categories": [],
            })
        start += page
        if len(entries) < page:
            break
        time.sleep(3)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("venue", nargs="?", help="iclr|neurips|icml|corl|icra|rss|… ")
    ap.add_argument("year", nargs="?", type=int, default=dt.date.today().year)
    ap.add_argument("--venueid", help="raw OpenReview venueid (overrides venue/year)")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--source", choices=["openreview", "arxiv"],
                    help="force a source (default: openreview if the venue has one)")
    args = ap.parse_args()
    if not args.venue and not args.venueid:
        ap.error("give a venue (e.g. `confscan.py corl 2026`) or --venueid")

    venue = (args.venue or "openreview").lower()
    label = f"{venue}-{args.year}" if args.venue else \
        re.sub(r"[^\w]+", "-", args.venueid).strip("-").lower()

    if args.venueid:
        cands = openreview_accepted(args.venueid)
    elif venue in OPENREVIEW and args.source != "arxiv":
        cands = openreview_accepted(OPENREVIEW[venue].format(y=args.year))
        if not cands:
            print(f"openreview returned nothing for {venue} {args.year} — "
                  f"decisions may not be out yet; trying arXiv comments…", file=sys.stderr)
            cands = arxiv_comment_search(f"{venue.upper()} {args.year}")
    else:
        cands = arxiv_comment_search(f"{venue.upper()} {args.year}")

    n_total = len(cands)
    if not cands:
        sys.exit(f"no accepted papers found for {label} — 放榜了吗？")

    # score with the same learned profile as fetch.py; dedup against the library
    items, existing_arxiv, existing_titles = P.library_index()
    weights = P.learn_profile(items, conf := P.load_conf())
    in_lib = [c for c in cands if c.get("arxiv") in existing_arxiv
              or P.norm_title(c["title"]) in existing_titles]
    cands = P.dedup(cands, existing_arxiv, existing_titles)
    for c in cands:
        P.score(c, weights, conf)
    cands.sort(key=lambda x: -x["_score"])
    picked = [c for c in cands if c["_score"] >= conf["min_score"]][:args.top]

    os.makedirs(OUTDIR, exist_ok=True)
    path = os.path.join(OUTDIR, f"{label}.md")
    L = ["---", f"title: {label}", "tags: [conf-scan, auto]", "---", "",
         f"# 📌 {label.upper()} 放榜扫描",
         "",
         f"*{dt.date.today().isoformat()} 扫描：接收列表 {n_total} 篇"
         f"（其中 {len(in_lib)} 篇已在你的库里），按你的兴趣画像排出 Top {len(picked)}。"
         f"`tools/confscan.py` 自动生成。*", ""]
    for i, c in enumerate(picked, 1):
        flag = {"oral": " 🏅oral", "spotlight": " ✨spotlight", "award": " 🏆"}.get(c.get("flag"), "")
        code = " 💻" if c.get("has_code") else ""
        hits = ", ".join(h for h in c["_hits"] if h not in ("code",)) or "—"
        L.append(f"### {i}. [{c['title']}]({c['url']}){flag}{code}")
        L.append(f"*score {c['_score']} · matched: {hits}*")
        ab = (c.get("abstract") or "")[:400]
        if ab:
            L.append(f"> {ab}…")
        L.append("")
    if in_lib:
        L.append("## 已在库里的接收论文")
        for c in in_lib:
            L.append(f"- {c['title']}")
        L.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    print(json.dumps([{"score": c["_score"], "title": c["title"], "url": c["url"],
                       "flag": c.get("flag", ""), "matched": c["_hits"]}
                      for c in picked], ensure_ascii=False, indent=2))
    print(f"\n{label}: {n_total} accepted scanned, {len(picked)} picked "
          f"→ {os.path.relpath(path, P.ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
