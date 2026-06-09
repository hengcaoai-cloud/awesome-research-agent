#!/usr/bin/env python3
"""Citation-graph exploration via Semantic Scholar.

Given an arXiv id (or S2 id), fetch the paper's references (what it builds on),
citations (what builds on it), and which of those are most influential — useful
for tracing a line of work and finding the current frontier.

Rate-limited without a key; set S2_API_KEY for reliability (free:
https://www.semanticscholar.org/product/api). Backs off on 429.

Usage:
    s2_graph.py 2603.23481                 # neighbours of one paper
    s2_graph.py 2603.23481 --citations 30  # more recent work citing it
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://api.semanticscholar.org/graph/v1"


def get(path, params, tries=4):
    key = os.environ.get("S2_API_KEY")
    headers = {"x-api-key": key} if key else {}
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < tries - 1:
                time.sleep(3 * (i + 1))
                continue
            sys.exit(f"S2 error {e.code}. Set S2_API_KEY for higher limits.")
        except Exception as e:
            sys.exit(f"S2 error: {e}")


def pid(ident):
    return f"ARXIV:{ident}" if __import__("re").fullmatch(r"\d{4}\.\d{4,5}", ident) else ident


def fmt(p):
    a = p.get("authors") or []
    who = (a[0]["name"].split()[-1] + " et al." if a else "?")
    cc = p.get("citationCount", 0)
    ax = (p.get("externalIds") or {}).get("ArXiv")
    tag = f"arXiv:{ax}" if ax else (p.get("venue") or "")
    return f"  [{cc:>5} cites] {p.get('year','?')} {who:20} {tag:14} {p.get('title','')[:60]}"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("id")
    ap.add_argument("--citations", type=int, default=20)
    ap.add_argument("--references", type=int, default=15)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    fields = "title,year,authors,citationCount,venue,externalIds"
    paper = get(f"/paper/{pid(args.id)}",
                {"fields": f"{fields},referenceCount,citationCount,abstract"})
    refs = get(f"/paper/{pid(args.id)}/references",
               {"fields": fields, "limit": args.references}).get("data", [])
    cites = get(f"/paper/{pid(args.id)}/citations",
                {"fields": fields, "limit": min(args.citations * 3, 100)}).get("data", [])

    ref_p = [r["citedPaper"] for r in refs if r.get("citedPaper")]
    cite_p = [c["citingPaper"] for c in cites if c.get("citingPaper")]
    ref_p.sort(key=lambda p: -(p.get("citationCount") or 0))
    # frontier = recent + influential papers citing this one
    cite_p.sort(key=lambda p: (-(p.get("year") or 0), -(p.get("citationCount") or 0)))
    cite_p = cite_p[:args.citations]

    if args.json:
        print(json.dumps({"paper": paper, "references": ref_p, "citations": cite_p},
                         ensure_ascii=False, indent=2))
        return
    print(f"# {paper.get('title','')}  ({paper.get('year','?')}, {paper.get('citationCount',0)} cites)\n")
    print("## Builds on (most influential references)")
    for p in ref_p:
        print(fmt(p))
    print("\n## Cited by / frontier (recent work building on it)")
    for p in cite_p:
        print(fmt(p))


if __name__ == "__main__":
    main()
