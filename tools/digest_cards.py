#!/usr/bin/env python3
"""Auto-generate value cards (problem / innovation / directions) for the latest
fetched papers and merge them into Inbox/.digest.json — so the knowledge-graph
cards are filled in automatically every day.

One batched `claude -p` call summarizes all papers that don't yet have a card
(idempotent: re-runs only fill the missing ones). Run after tools/fetch.py.

Usage:
    python3 tools/digest_cards.py [--all]   # --all regenerates even existing cards
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import llm  # provider-agnostic agent CLI (Claude Code or OpenAI Codex)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "Inbox")
LAST = os.path.join(INBOX, ".last_fetch.json")
DIGEST = os.path.join(INBOX, ".digest.json")

PROMPT_HEAD = """You are triaging freshly fetched papers for a researcher whose focus is
embodied AI — embodied foundation models (world models / WAM, VLA), representation
learning (esp. for embodied AI), and 3D/4D vision. For EACH paper below, using only
its title and abstract (do not invent results), write a concise value card:
- "problem": the gap it addresses (1 sentence)
- "innovation": the core new idea, concretely (1-2 sentences)
- "directions": one potential follow-up direction toward embodied intelligence (1 sentence)

Output ONLY a JSON array — one object per paper, in order, each exactly:
{"id": "<the id shown>", "problem": "...", "innovation": "...", "directions": "..."}
No markdown, no commentary.

Papers:
"""


def load_json(path, default):
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            return default
    return default


def digest_list():
    """Return digest as a list of dicts (normalizing legacy dict form)."""
    d = load_json(DIGEST, [])
    if isinstance(d, dict):
        return [{"arxiv": k, **(v if isinstance(v, dict) else {})} for k, v in d.items()]
    return d if isinstance(d, list) else []


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="regenerate even existing cards")
    args = ap.parse_args()

    last = load_json(LAST, {})
    papers = last.get("papers", [])
    if not papers:
        print("no fetched papers (run tools/fetch.py first)")
        return

    digest = digest_list()
    have = {str(x.get("arxiv") or x.get("id")): x for x in digest}
    todo = []
    for p in papers:
        pid = str(p.get("id") or "")
        if not pid:
            continue
        card = have.get(pid)
        has = card and (card.get("problem") or card.get("innovation"))
        if has and not args.all:
            continue
        todo.append(p)

    if not todo:
        print("all cards already present; nothing to do")
        return

    lines = []
    for i, p in enumerate(todo, 1):
        ab = (p.get("abstract") or "").strip().replace("\n", " ")[:1400]
        lines.append(f"[{i}] id={p.get('id')} | {p.get('title','')}\nAbstract: {ab}\n")
    prompt = PROMPT_HEAD + "\n".join(lines)

    print(f"generating {len(todo)} card(s) via {llm.cli_name()}…", file=sys.stderr)
    ok, out = llm.complete(prompt)
    if not ok:
        sys.exit(out)
    m = re.search(r"\[\s*\{.*\}\s*\]", out, re.S)
    if not m:
        sys.exit("could not parse a JSON array from claude output:\n" + out[:400])
    try:
        cards = json.loads(m.group(0))
    except Exception as e:
        sys.exit(f"JSON parse error: {e}\n{m.group(0)[:400]}")

    # merge by id
    by_id = {str(x.get("arxiv") or x.get("id")): x for x in digest}
    n_new = 0
    for c in cards:
        pid = str(c.get("id") or "")
        if not pid:
            continue
        tgt = by_id.get(pid)
        if tgt is None:
            tgt = {"arxiv": pid}
            digest.insert(0, tgt)
            by_id[pid] = tgt
        for k in ("problem", "innovation", "directions"):
            if c.get(k):
                tgt[k] = c[k].strip()
        n_new += 1

    json.dump(digest, open(DIGEST, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"wrote {n_new} value card(s) → Inbox/.digest.json")


if __name__ == "__main__":
    main()
