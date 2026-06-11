#!/usr/bin/env python3
"""研究雷达: match freshly fetched papers against the user's OPEN QUESTIONS
(Research/questions.md, one `## ` section each) and IDEA files
(Research/ideas/*.md).

One batched LLM call (tools/llm.py) judges which of today's papers genuinely
bear on which question/idea, with a relation type:
    同问题  — attacks the same question
    组件    — provides a usable method/component toward it
    撞车    — already realizes the idea's core (novelty risk!)
    旁证    — evidence for/against the underlying hypothesis

Hits accumulate in Research/radar.md (grouped by question/idea, dated) and the
day's new hits are appended to Daily/<today>.md. History lives in
Research/.radar.json; a (paper, target) pair is never reported twice.

Run after fetch.py + digest_cards.py (daily.sh does). Stdlib only.

Usage:
    radar.py [--dry-run] [--all]    # --all re-matches even already-seen pairs
"""
import argparse
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import llm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "Inbox")
RESEARCH = os.path.join(ROOT, "Research")
QUESTIONS = os.path.join(RESEARCH, "questions.md")
IDEAS = os.path.join(RESEARCH, "ideas")
RADAR_MD = os.path.join(RESEARCH, "radar.md")
HISTORY = os.path.join(RESEARCH, ".radar.json")

RELATIONS = ("同问题", "组件", "撞车", "旁证")

PROMPT_HEAD = """你在为一位具身智能研究者做"研究雷达"。下面有 (A) 他关心的开放问题/研究想法，
(B) 今天新抓取的论文。判断每篇论文是否与某个问题/想法**真正相关**，宁缺毋滥——
只有当论文的核心贡献对该问题有实质意义时才算命中，泛泛的领域重叠不算。

关系类型(relation)只能取:
- "同问题": 论文直接研究同一个问题
- "组件": 论文提供了可直接用于解决该问题的方法/模块/数据
- "撞车": 论文已经实现了该想法的核心(新颖性风险, 对 idea 类目标尤其重要)
- "旁证": 论文为该问题背后的假设提供了支持或反对的证据

只输出一个 JSON 数组(可以为空), 每个命中一个对象, 格式严格为:
{"paper": "<论文id>", "target": "<目标id>", "relation": "<上述四选一>", "why": "<一两句中文, 说清这篇论文的哪个具体创新点和该问题怎么对上>"}
不要输出 markdown 或其他文字。

(A) 开放问题 / 想法:
"""


def load_json(path, default):
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            return default
    return default


def qid(head):
    """Stable id for a question heading (also used by viz.py's web panel)."""
    return "q:" + re.sub(r"[^\w一-鿿]+", "-", head)[:60].strip("-")


def load_targets():
    """Return [{id, kind, title, text}] from questions.md sections + ideas/*.md."""
    out = []
    if os.path.exists(QUESTIONS):
        text = open(QUESTIONS, encoding="utf-8").read()
        # sections: '## heading' ... until next '## ' or EOF
        for m in re.finditer(r"^## +(.+?)\s*$\n(.*?)(?=^## |\Z)", text, re.M | re.S):
            head, body = m.group(1).strip(), m.group(2).strip()
            if "✅" in head or head.startswith("示例"):
                continue
            out.append({"id": qid(head), "kind": "question", "title": head,
                        "text": body[:900]})
    if os.path.isdir(IDEAS):
        for fn in sorted(os.listdir(IDEAS)):
            if not fn.endswith(".md"):
                continue
            text = open(os.path.join(IDEAS, fn), encoding="utf-8").read()
            text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)  # strip frontmatter
            m = re.search(r"^# +(.+)$", text, re.M)
            title = m.group(1).strip() if m else fn[:-3]
            if "✅" in title:
                continue
            out.append({"id": "i:" + fn[:-3], "kind": "idea", "title": title,
                        "text": text.strip()[:1100]})
    return out


def load_papers():
    """Today's fetched papers, enriched with digest value cards when present."""
    last = load_json(os.path.join(INBOX, ".last_fetch.json"), {})
    papers = [p for p in last.get("papers", []) if p.get("id")]
    cards = load_json(os.path.join(INBOX, ".digest.json"), [])
    if isinstance(cards, dict):
        cards = [{"arxiv": k, **v} for k, v in cards.items() if isinstance(v, dict)]
    by_id = {str(c.get("arxiv") or c.get("id")): c for c in cards}
    for p in papers:
        c = by_id.get(str(p["id"]), {})
        p["innovation"] = c.get("innovation", "")
        p["problem"] = c.get("problem", "")
    return papers, last.get("date") or dt.date.today().isoformat()


def build_prompt(targets, papers):
    lines = []
    for t in targets:
        lines.append(f"[{t['id']}] ({'想法' if t['kind'] == 'idea' else '问题'}) "
                     f"{t['title']}\n{t['text']}\n")
    lines.append("\n(B) 今天的论文:\n")
    for p in papers:
        ab = (p.get("abstract") or "").replace("\n", " ")[:900]
        card = ""
        if p.get("innovation"):
            card = f"\n创新点: {p['innovation']}"
        lines.append(f"[{p['id']}] {p['title']}{card}\n摘要: {ab}\n")
    return PROMPT_HEAD + "\n".join(lines)


def render_radar_md(history):
    """Regenerate Research/radar.md from full history (idempotent)."""
    by_target = {}
    for h in history:
        by_target.setdefault(h["target"], []).append(h)
    L = ["---", "title: radar", "tags: [radar, auto]", "---", "",
         "# 📡 研究雷达",
         "",
         "*自动生成（`tools/radar.py`，每日 fetch 后运行）— 新论文与 [[questions|开放问题]] "
         "和 `Research/ideas/` 的命中记录，按目标分组、新的在前。不要手改；"
         "问题本身去 [[questions]] 里编辑。*", ""]
    icon = {"question": "❓", "idea": "💡"}
    order = sorted(by_target.values(), key=lambda hs: max(h["date"] for h in hs),
                   reverse=True)
    for hs in order:
        hs.sort(key=lambda h: h["date"], reverse=True)
        t = hs[0]
        L.append(f"## {icon.get(t['target_kind'], '❓')} {t['target_title']}")
        L.append("")
        for h in hs:
            risk = " ⚠️" if h["relation"] == "撞车" else ""
            L.append(f"- **{h['date']}** [{h['paper_title']}]({h['url']}) — "
                     f"**{h['relation']}**{risk}：{h['why']}")
        L.append("")
    with open(RADAR_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def append_daily(hits, date):
    path = os.path.join(ROOT, "Daily", f"{date}.md")
    L = ["", "### 📡 Radar", ""]
    for h in hits:
        L.append(f"- [{h['paper_title']}]({h['url']}) → **{h['target_title']}** "
                 f"（{h['relation']}）：{h['why']}")
    L.append("")
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="print prompt + matches, write nothing")
    ap.add_argument("--all", action="store_true", help="re-match pairs seen before")
    args = ap.parse_args()

    targets = load_targets()
    if not targets:
        print("radar: no open questions/ideas yet — add some to Research/questions.md")
        return
    papers, date = load_papers()
    if not papers:
        print("radar: no fetched papers (run tools/fetch.py first)")
        return

    history = load_json(HISTORY, [])
    seen = {(h["paper"], h["target"]) for h in history}
    seen |= {tuple(x) for x in load_json(HISTORY + ".seen", [])}
    if not args.all:
        # skip papers already matched against every current target
        tids = {t["id"] for t in targets}
        papers = [p for p in papers
                  if not tids <= {t for pp, t in seen if pp == str(p["id"])}]
    if not papers:
        print("radar: all of today's papers already matched; nothing to do")
        return

    prompt = build_prompt(targets, papers)
    print(f"radar: matching {len(papers)} paper(s) × {len(targets)} target(s) "
          f"via {llm.cli_name()}…", file=sys.stderr)
    ok, out = llm.complete(prompt)
    if not ok:
        sys.exit("radar: llm failed: " + out)
    m = re.search(r"\[[\s\S]*\]", out)
    if not m:
        sys.exit("radar: could not parse JSON array from output:\n" + out[:400])
    try:
        matches = json.loads(m.group(0))
    except Exception as e:
        sys.exit(f"radar: JSON parse error: {e}\n{m.group(0)[:400]}")

    t_by_id = {t["id"]: t for t in targets}
    p_by_id = {str(p["id"]): p for p in papers}
    today = dt.date.today().isoformat()
    new_hits = []
    for c in matches:
        t = t_by_id.get(str(c.get("target", "")))
        p = p_by_id.get(str(c.get("paper", "")))
        if not t or not p or c.get("relation") not in RELATIONS:
            continue
        if (str(p["id"]), t["id"]) in seen:
            continue
        new_hits.append({
            "date": today, "paper": str(p["id"]), "paper_title": p["title"],
            "url": (f"https://arxiv.org/abs/{p['id']}"
                    if re.fullmatch(r"\d{4}\.\d{4,5}", str(p["id"]))
                    else f"https://www.semanticscholar.org/paper/{p['id']}"),
            "target": t["id"], "target_kind": t["kind"], "target_title": t["title"],
            "relation": c["relation"], "why": str(c.get("why", "")).strip(),
        })
        seen.add((str(p["id"]), t["id"]))

    if args.dry_run:
        print(json.dumps(new_hits, ensure_ascii=False, indent=2))
        return

    history.extend(new_hits)
    # persist the no-hit pairs separately so history stays clean
    misses = load_json(HISTORY + ".seen", [])
    miss_set = {tuple(x) for x in misses}
    hit_set = {(h["paper"], h["target"]) for h in history}
    for p in papers:
        for t in targets:
            pair = (str(p["id"]), t["id"])
            if pair not in hit_set:
                miss_set.add(pair)
    json.dump(sorted(miss_set), open(HISTORY + ".seen", "w", encoding="utf-8"))
    json.dump(history, open(HISTORY, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    if history:
        render_radar_md(history)
    if new_hits:
        append_daily(new_hits, date)
        print(f"radar: {len(new_hits)} hit(s) → Research/radar.md + Daily/{date}.md")
        for h in new_hits:
            print(f"  · {h['paper_title'][:60]} → {h['target_title'][:40]} ({h['relation']})")
    else:
        print("radar: no hits today")


if __name__ == "__main__":
    main()
