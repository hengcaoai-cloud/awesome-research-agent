#!/usr/bin/env python3
"""概念词汇表: build Topics/Concepts.md — a cross-paper concept MOC.

Scans every Literature/ note and maps each specific concept (the same lexicon
viz.py uses for graph edges, plus your .interests.yaml boost terms) to the
papers that discuss it. A paper counts as **engaged** with a concept when the
concept appears in YOUR highlights or your synthesis half — engaged links are
listed first and bold.

Definitions (1-2 句中文, in the embodied-AI context) are generated once per
new concept via tools/llm.py and cached in Topics/.glossary.json; re-runs are
cheap and only define concepts that appeared since.

The bottom half of Topics/Concepts.md (below the standard marker) is yours and
is never overwritten. Stdlib only.

Usage:
    glossary.py [--no-llm] [--min-papers 2]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import llm
import paperlib as P
import viz as V

LIT = os.path.join(P.ROOT, "Literature")
TOPICS = os.path.join(P.ROOT, "Topics")
OUT = os.path.join(TOPICS, "Concepts.md")
CACHE = os.path.join(TOPICS, ".glossary.json")

DEF_PROMPT = """为下面这些机器学习/具身智能领域的概念各写一个简明定义：1-2 句中文，
面向一位具身智能研究者，说清它是什么、解决什么问题。技术名词可保留英文。
只输出一个 JSON 对象 {"<概念>": "<定义>", ...}，不要 markdown、不要其他文字。

概念列表:
"""


def lexicon():
    """Specific concepts only: viz edge keywords + boost terms minus broad ones."""
    lex = set(V.EDGE_KW)
    for k in P.load_conf().get("boost", {}):
        k = V.SYN.get(k.lower(), k.lower())
        if k not in V.GENERIC and k != "code" and len(k) > 2:
            lex.add(k)
    return lex


def scan_notes(lex):
    """concept -> {note_stem: level}; level 2 = in highlights/your half, 1 = mentioned."""
    hits = {}
    titles = {}
    if not os.path.isdir(LIT):
        return hits, titles
    for fn in sorted(os.listdir(LIT)):
        if not fn.endswith(".md"):
            continue
        stem = fn[:-3]
        text = open(os.path.join(LIT, fn), encoding="utf-8").read()
        m = re.search(r'^title:\s*"?(.+?)"?\s*$', text[:600], re.M)
        titles[stem] = (m.group(1) if m else stem)[:80]
        if P.MARKER in text:
            managed, yours = text.split(P.MARKER, 1)
        else:
            managed, yours = text, ""
        hm = re.search(r"## My Highlights.*", managed, re.S)
        engaged = ((hm.group(0) if hm else "") + " " + yours).lower()
        full = text.lower()
        for kw in lex:
            if V.kw_in(full, kw):
                level = 2 if V.kw_in(engaged, kw) else 1
                hits.setdefault(kw, {})[stem] = level
    return hits, titles


def define_missing(concepts, cache, no_llm):
    todo = [c for c in concepts if c not in cache]
    if not todo or no_llm or not llm.available():
        return cache
    print(f"defining {len(todo)} new concept(s) via {llm.cli_name()}…", file=sys.stderr)
    ok, out = llm.complete(DEF_PROMPT + "\n".join(f"- {c}" for c in sorted(todo)))
    if not ok:
        print("warn: llm failed, definitions skipped: " + out[:200], file=sys.stderr)
        return cache
    m = re.search(r"\{[\s\S]*\}", out)
    if m:
        try:
            for k, v in json.loads(m.group(0)).items():
                if k in concepts and isinstance(v, str):
                    cache[k] = v.strip()
        except Exception as e:
            print(f"warn: definition JSON parse error: {e}", file=sys.stderr)
    return cache


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-llm", action="store_true", help="skip definition generation")
    ap.add_argument("--min-papers", type=int, default=2,
                    help="hide concepts appearing in fewer notes")
    args = ap.parse_args()

    lex = lexicon()
    hits, titles = scan_notes(lex)
    concepts = {c: m for c, m in hits.items() if len(m) >= args.min_papers}
    if not concepts:
        sys.exit("no concepts found — is Literature/ empty?")

    cache = {}
    if os.path.exists(CACHE):
        try:
            cache = json.load(open(CACHE, encoding="utf-8"))
        except Exception:
            cache = {}
    cache = define_missing(set(concepts), cache, args.no_llm)
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # preserve the user's half of an existing Concepts.md
    yours = None
    if os.path.exists(OUT):
        old = open(OUT, encoding="utf-8").read()
        if P.MARKER in old:
            yours = old[old.index(P.MARKER):]
    if yours is None:
        yours = P.MARKER + "\n\n## Notes\n*概念之间的联系、你自己的理解，写在这里，重建不会动。*\n- \n"

    def order(c):
        m = concepts[c]
        eng = sum(1 for v in m.values() if v == 2)
        return (-eng, -len(m), c)

    n_eng = lambda m: sum(1 for v in m.values() if v == 2)
    L = ["---", "title: Concepts", "tags: [glossary, MOC]", "---", "",
         "# 🧠 概念词汇表",
         "",
         f"*自动生成（`tools/glossary.py`）：{len(concepts)} 个跨论文概念。"
         "**加粗** = 该概念出现在你的高亮/综合里（真正读过的信号），"
         "普通链接 = 论文提及。按高亮论文数排序。*", ""]
    for c in sorted(concepts, key=order):
        m = concepts[c]
        eng = sorted([s for s, v in m.items() if v == 2])
        men = sorted([s for s, v in m.items() if v == 1])
        L.append(f"## {c}")
        if cache.get(c):
            L.append(f"> {cache[c]}")
        parts = [f"**[[{s}|{titles[s]}]]**" for s in eng]
        parts += [f"[[{s}|{titles[s]}]]" for s in men]
        L.append(f"\n*{len(m)} papers（{n_eng(m)} 高亮）:* " + " · ".join(parts))
        L.append("")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n" + yours)
    print(f"wrote Topics/Concepts.md  ({len(concepts)} concepts, "
          f"{sum(n_eng(m) for m in concepts.values())} engaged links)")


if __name__ == "__main__":
    main()
