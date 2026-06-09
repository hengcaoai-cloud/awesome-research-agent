#!/usr/bin/env python3
"""Fetch relevant new papers from arXiv (freshness) + Semantic Scholar
recommendations (interest-adaptive), merge, score, and surface the top N to
Inbox/.

The interest profile is learned every run from the Zotero library (highlighted
papers weighted higher) plus .interests.yaml, and S2 recommendations are seeded
by the library itself — so the agent adapts as the library grows.

Usage:
    fetch.py [--dry-run] [--top N] [--source arxiv|s2|both]
"""
import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paperlib as P


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--top", type=int)
    ap.add_argument("--days", type=int,
                    help="override lookback window (one-off catch-up over older arXiv)")
    ap.add_argument("--source", choices=["arxiv", "s2", "both"], default="both")
    args = ap.parse_args()

    conf = P.load_conf()
    if args.days:
        conf["lookback_days"] = args.days
    items, existing_arxiv, existing_titles = P.library_index()
    weights = P.learn_profile(items, conf)
    pos_ids, neg_ids = P.load_feedback()
    surfaced = P.load_surfaced()
    cutoff = (dt.date.today() - dt.timedelta(days=conf["lookback_days"])).isoformat()

    def ident(c):
        return c.get("arxiv") or c.get("s2id") or P.norm_title(c["title"])

    raw = []
    if args.source in ("arxiv", "both"):
        raw += P.arxiv_recall(conf, cutoff)
    if args.source in ("s2", "both"):
        raw += P.s2_recall(items, conf, neg_ids, pos_ids)

    raw = [c for c in raw if c["title"] and not P.muted(c, conf)]
    raw = P.dedup(raw, existing_arxiv, existing_titles)
    raw = [c for c in raw if ident(c) not in surfaced]   # never resurface
    for c in raw:
        P.score(c, weights, conf)
    raw = [c for c in raw if c["_score"] >= conf["min_score"]]
    raw.sort(key=lambda x: -x["_score"])

    # per-source quotas so daily freshness (arxiv) is never crowded out by S2
    q_arxiv = int(conf.get("top_arxiv", 8))
    q_s2 = int(conf.get("top_s2", 6))
    if args.top:                       # --top overrides: single merged ranking
        q_arxiv, q_s2 = args.top, args.top
    fresh = [c for c in raw if c["source"] == "arxiv"][:q_arxiv]
    recs = [c for c in raw if c["source"] == "s2"][:q_s2]
    picked = fresh + recs

    if not args.dry_run:
        for c in picked:
            c["_path"] = os.path.relpath(P.write_stub(c), P.ROOT)
        P.mark_surfaced(ident(c) for c in picked)

    summary = [{
        "score": c["_score"], "source": c["source"], "title": c["title"],
        "matched": c["_hits"], "published": c.get("published"),
        "abstract": c.get("abstract", ""),
        "id": c.get("arxiv") or c.get("s2id"), "path": c.get("_path"),
    } for c in picked]
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # Machine-readable copy for downstream tooling (viz.py builds the graph from it).
    if not args.dry_run:
        with open(os.path.join(P.INBOX, ".last_fetch.json"), "w", encoding="utf-8") as f:
            json.dump({"date": dt.date.today().isoformat(), "papers": summary},
                      f, ensure_ascii=False, indent=2)

    n_arxiv = sum(1 for c in raw if c["source"] == "arxiv")
    n_s2 = sum(1 for c in raw if c["source"] == "s2")
    print(f"\nrelevant: {len(raw)} (arxiv {n_arxiv}, s2 {n_s2}); surfaced "
          f"{len(fresh)} fresh + {len(recs)} recommended; cutoff {cutoff}", file=sys.stderr)


if __name__ == "__main__":
    main()
