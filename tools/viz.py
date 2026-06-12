#!/usr/bin/env python3
"""Interactive knowledge graph of today's fetched papers + live feedback.

Reads the latest fetch (Inbox/.last_fetch.json), optional value cards
(Inbox/.digest.json) and the existing library (Literature/*.md). Builds a graph
that links each new paper to (a) the user's interest AREAS and (b) the specific
library papers it actually shares concepts with — relatedness is computed from
overlapping *specific* interest keywords (broad words like "robot"/"manipulation"
are ignored so edges stay meaningful). Writes a self-contained HTML to
Daily/<date>-graph.html.

Two modes:
    python3 tools/viz.py [--date YYYY-MM-DD] [--open]   # write static HTML
    python3 tools/viz.py --serve [--port 8765] [--date] # live: 👍/👎/➕ buttons
                                                         # call feedback.py /
                                                         # zotero_add.py in place

In --serve mode the per-paper detail panel has buttons that teach the fetcher
(👍 more like this → feedback keep, 👎 less → feedback drop) and ➕ save the paper
to Zotero with its PDF — so judging value and steering recommendations happen
right in the graph.
"""
import argparse
import datetime as dt
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import webbrowser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
INBOX = os.path.join(ROOT, "Inbox")
LIT = os.path.join(ROOT, "Literature")
TOPICS = os.path.join(ROOT, "Topics")
DAILY = os.path.join(ROOT, "Daily")
PDFCACHE = os.path.join(INBOX, ".pdfcache")
PY = sys.executable or "python3"
MARKER_NOTE = "<!-- ===== Below this line is yours; sync never touches it ===== -->"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import llm  # provider-agnostic agent CLI (Claude Code or OpenAI Codex)

# Deep-read template (the user's 6-section method-analysis prompt). Filled with the
# PDF path and run via `claude -p` on demand from the value card.
DEEP_PROMPT = """你是一名 AI 领域的研究生，擅长从第一性原理思考问题，目标是深入理解论文的方法部分（动机、设计逻辑、流程细节、优势与不足），以便学习和在研究中借鉴。

下面给出一篇论文的全文（由 arXiv HTML 提取，可能含少量解析噪声）。请基于它**全程用中文**、严格按下面 6 个大点及其子点输出 **markdown**，重点解析**方法(Methodology)**，弱化引言与结论，不要杜撰论文中没有的内容：

0. 翻译摘要原文
1. 方法动机：1)解决什么问题(尽量形式化) 2)传统方法的挑战/局限 3)作者为何提出该方法 4)研究假设/insight 5)该 insight 受什么启发
2. 方法设计(**最重要、必须非常细致**)：1)清晰的 pipeline，逐步 输入→处理→输出，讲清每步具体操作与技术细节 2)若涉及数据集，说明收集/清洗/标注与构成 3)若涉及模型结构，描述每个模块功能及如何协同 4)若有公式/算法，用通俗语言解释其意义与作用
3. 与其他方法对比：1)与主流方法的本质不同 2)创新点，每条严格按【创新点解决的问题】→【受哪个 insight 启发】→【设计了什么创新点，尽量具体】 3)更适用的场景 4)用 markdown **表格**总结对比(优点/缺点/改进点) 5)局限与可延伸的新情境
4. 实验表现与优势：1)如何验证有效性(实验设计与设置) 2)在哪些指标上超越对比方法(列关键数据) 3)是否有说服力、还可补哪些实验 4)局限性(泛化/开销/数据依赖)
5. 学习与应用：1)是否开源、复现关键步骤 2)需注意的超参数/数据预处理/训练细节 3)能否迁移到其他任务、如何迁移
6. 总结：1)一句话核心思想(≤20字) 2)以问句形式还原想到该 idea 的第一性原理路径(如「之前的方法…，那可不可以试试 xxx」) 3)速记版 pipeline(3-5 步，不用论文术语，直白到只看它就能大体理解)

只输出这份分析本身，不要额外寒暄。

================ 论文全文开始 ================
{text}
================ 论文全文结束 ================"""

ASK_PROMPT = """你是一位严谨的论文阅读助手。请基于下面提供的论文原文回答用户的问题，要求：
- **只依据论文原文**回答；论文没讲的就明确说"论文中没有提到"，不要编造、不要用领域常识冒充论文内容
- 回答精准、结构清晰、通俗易懂（中文，技术名词可保留英文）
- 关键结论附上论文中的依据：引用原文短句（可用引号）并尽量给出小节/公式/图表编号，让用户能在原文里定位
- 默认控制在 300 字以内；问题确实复杂时可以更长，但不要灌水

{history}================ 论文原文开始 ================
{text}
================ 论文原文结束 ================

用户问题：{q}

直接输出回答，不要寒暄。"""

# Interest keyword -> area (mirrors .interests.yaml boost terms). Grouping is what
# the graph shows: "how does this paper relate to my areas?"
# Calibrated to the user's Zotero (World Model 33, VLA 33, CV 27, Robotics 20, …)
# and stated focus: embodied FMs, representation learning (esp. embodied), 3D/4D vision.
AREAS = {
    "Embodied FM · WAM/VLA": [
        "world model", "world action model", "wam", "vision-language-action",
        "vla", "embodied foundation model", "embodied"],
    "Representation learning": [
        "representation learning", "self-supervised", "masked autoencoder", "jepa",
        "joint embedding", "representation autoencoder", "contrastive learning",
        "action representation", "action-centric representation", "latent action",
        "representation for action", "representation for control",
        "representation for policy", "pretrained visual representation",
        "visual representation", "sensorimotor representation", "state representation"],
    "3D/4D vision": [
        "3d scene", "point cloud", "scene flow", "optical flow", "reconstruction",
        "dynamic scene", "neural rendering", "gaussian splatting", "nerf",
        "novel view", "visual geometry", "geometry", "depth estimation",
        "spatial intelligence", "spatial reasoning", "4d"],
    "Robotics · manipulation": [
        "manipulation", "tactile", "contact-rich", "dexterous", "grasping",
        "imitation learning", "diffusion policy", "policy learning", "robot"],
    "Vision · MLLM · generative": [
        "multimodal large language model", "vision foundation model",
        "vision-language", "image generation", "video generation", "diffusion model",
        "flow matching", "diffusion transformer", "foundation model"],
}
AREA_COLOR = {
    "Embodied FM · WAM/VLA": "#e6557a",
    "Representation learning": "#7a5cd0",
    "3D/4D vision": "#3aa0e0",
    "Robotics · manipulation": "#e0913a",
    "Vision · MLLM · generative": "#3ab07a",
    "_other": "#8a90a4",
}
# Broad, near-ubiquitous terms — used for AREA placement only, never to form edges
# (else "everything VLA" links to everything).
GENERIC = {"robot", "manipulation", "embodied", "foundation model", "3d scene",
           "code", "vla", "vision-language-action", "world model",
           "embodied foundation model", "vision-language", "geometry"}
# Specific sub-concepts whose overlap means two papers are genuinely related.
EDGE_KW = {
    "latent action", "world action model", "action representation",
    "action-centric representation", "representation for action",
    "representation for control", "representation for policy",
    "representation learning", "self-supervised", "masked autoencoder", "jepa",
    "joint embedding", "representation autoencoder", "contrastive learning",
    "pretrained visual representation", "visual representation",
    "sensorimotor representation", "state representation",
    "tactile", "contact-rich", "dexterous", "grasping", "imitation learning",
    "diffusion policy", "point cloud", "scene flow", "optical flow",
    "reconstruction", "dynamic scene", "neural rendering", "gaussian splatting",
    "nerf", "novel view", "visual geometry", "depth estimation",
    "spatial intelligence", "spatial reasoning", "4d", "flow matching",
    "video generation", "image generation", "diffusion transformer",
    "multimodal large language model", "vision foundation model"}
# Sharing one of these alone is already a strong relatedness signal (double weight).
STRONG = {"latent action", "world action model", "action representation",
          "representation learning", "jepa", "masked autoencoder",
          "tactile", "contact-rich", "point cloud", "scene flow",
          "gaussian splatting", "neural rendering", "spatial intelligence",
          "diffusion policy", "flow matching", "video generation"}
SYN = {"wam": "world action model", "v-jepa": "jepa", "vjepa": "jepa"}  # synonyms

ALL_KW = sorted({k for ks in AREAS.values() for k in ks}, key=len, reverse=True)


def edge_concepts(kws):
    out = set()
    for k in kws:
        k = SYN.get(k.lower(), k.lower())
        if k in EDGE_KW:
            out.add(k)
    return out


_GREEK = {"alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
          "zeta": "ζ", "eta": "η", "theta": "θ", "iota": "ι", "kappa": "κ",
          "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ",
          "sigma": "σ", "tau": "τ", "phi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω"}
_SUB = {c: s for c, s in zip("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")}
_SUP = {c: s for c, s in zip("0123456789+-=()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ")}


def clean_label(s):
    """Render a title's LaTeX as plain unicode for the canvas (no MathJax there)."""
    s = s.replace("$", "")
    for k, v in _GREEK.items():
        s = s.replace("\\" + k, v)
    s = re.sub(r"_\{?([0-9+\-=()])\}?", lambda m: _SUB.get(m.group(1), m.group(1)), s)
    s = re.sub(r"\^\{?([0-9+\-=()n])\}?", lambda m: _SUP.get(m.group(1), m.group(1)), s)
    s = re.sub(r"\\[a-zA-Z]+", " ", s)        # drop remaining LaTeX commands
    s = s.replace("{", "").replace("}", "").replace("\\", "")
    return re.sub(r"\s{2,}", " ", s).strip()


def kw_in(text, kw):
    """Substring for multiword phrases, word-boundary for short tokens."""
    if " " in kw or "-" in kw:
        return kw in text
    return re.search(r"\b" + re.escape(kw) + r"\b", text) is not None


def keywords_of(text):
    t = text.lower()
    return {k for k in ALL_KW if kw_in(t, k)}


def area_of_keywords(kws):
    """Dominant area = the area with the most matched keywords."""
    best, best_n = "_other", 0
    for area, aks in AREAS.items():
        n = sum(1 for k in kws if k in aks)
        if n > best_n:
            best, best_n = area, n
    return best


def load_last_fetch(date):
    p = os.path.join(INBOX, ".last_fetch.json")
    if os.path.exists(p):
        d = json.load(open(p, encoding="utf-8"))
        if not date or d.get("date") == date:
            return d.get("date"), d.get("papers", [])
    date = date or dt.date.today().isoformat()
    papers = []
    for f in sorted(glob.glob(os.path.join(INBOX, f"{date}-*.md"))):
        t = open(f, encoding="utf-8").read()
        def g(k):
            m = re.search(rf"^{k}:\s*(.*)$", t, re.M)
            return m.group(1).strip() if m else ""
        mm = re.search(r"^matched:\s*\[(.*)\]", t, re.M)
        matched = [x.strip().strip('"') for x in mm.group(1).split(",")] if mm else []
        ab = re.search(r"## Abstract\n(.*?)\n\n", t, re.S)
        papers.append({"id": g("arxiv") or g("s2id"), "title": g("title").strip('"'),
                       "score": float(g("score") or 0), "source": g("source"),
                       "matched": [x for x in matched if x], "published": g("published"),
                       "abstract": ab.group(1).strip() if ab else ""})
    return date, papers


def load_digest():
    p = os.path.join(INBOX, ".digest.json")
    if not os.path.exists(p):
        return {}
    try:
        data = json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(data, list):
        return {str(x.get("arxiv") or x.get("id")): x for x in data}
    return {str(k): v for k, v in data.items()}


def library_index():
    """Each note -> {title, collections, kws (from title+abstract)}."""
    out = []
    for f in glob.glob(os.path.join(LIT, "*.md")):
        t = open(f, encoding="utf-8").read(6000)
        m = re.search(r'^title:\s*"?(.*?)"?\s*$', t, re.M)
        if not (m and m.group(1).strip()):
            continue
        title = m.group(1).strip()
        ab = re.search(r"## Abstract\n(.*?)\n\n", t, re.S)
        text = title + " " + (ab.group(1) if ab else "")
        cm = re.search(r"^collections:\s*\[(.*)\]", t, re.M)
        colls = [c.strip().strip('"') for c in cm.group(1).split(",")] if cm else []
        am = re.search(r"^zotero_added:\s*(\d{4}-\d{2}-\d{2})", t, re.M)
        kws = keywords_of(text)
        out.append({"title": title, "colls": colls, "kws": kws,
                    "ek": edge_concepts(kws), "added": am.group(1) if am else "",
                    "note": os.path.splitext(os.path.basename(f))[0]})
    return out


def build_graph(papers, digest, lib, date=None):
    nodes, edges, node_ids = [], [], set()

    def add(nid, **kw):
        if nid not in node_ids:
            nodes.append(dict(id=nid, **kw)); node_ids.add(nid)

    def rel(a, b):
        """Relatedness = shared specific EDGE concepts; STRONG ones count double."""
        shared = a & b
        if not shared:
            return 0, []
        w = sum(2 if k in STRONG else 1 for k in shared)
        return w, sorted(shared)

    touched = set()
    paper_kw = {}
    # paper nodes + paper→area edges
    for p in papers:
        pid = "P:" + (p.get("id") or p["title"][:24])
        matched = [m.lower() for m in (p.get("matched") or [])]
        paper_kw[pid] = edge_concepts(matched)
        dom = area_of_keywords(matched)
        d = digest.get(str(p.get("id")), {})
        is_arxiv = bool(p.get("id") and re.match(r"\d{4}\.\d", str(p["id"])))
        add(pid, label=clean_label(p["title"]), type="paper", area=dom,
            score=round(float(p.get("score") or 0), 1),
            detail={"title": p["title"], "id": p.get("id"), "source": p.get("source"),
                    "score": round(float(p.get("score") or 0), 1), "matched": p.get("matched") or [],
                    "url": f"https://arxiv.org/abs/{p['id']}" if is_arxiv else "",
                    "arxiv": p.get("id") if is_arxiv else "",
                    "problem": d.get("problem", ""), "innovation": d.get("innovation", ""),
                    "directions": d.get("directions", ""), "deep": d.get("deep", ""),
                    "abstract": (p.get("abstract") or "")[:1000]})
        for area, aks in AREAS.items():
            if any(m in aks for m in matched):
                touched.add(area)
                edges.append({"s": pid, "t": "A:" + area, "w": 1, "kind": "area"})
        if dom == "_other":
            touched.add("_other"); edges.append({"s": pid, "t": "A:_other", "w": 1, "kind": "area"})

    for area in touched:
        add("A:" + area, label="Other" if area == "_other" else area, type="area",
            area=area, detail={"title": "Other" if area == "_other" else area, "kind": "interest area"})

    # paper ↔ paper (today's batch) by shared specific concepts
    pids = list(paper_kw)
    for i in range(len(pids)):
        for j in range(i + 1, len(pids)):
            w, sh = rel(paper_kw[pids[i]], paper_kw[pids[j]])
            if w >= 2:  # share ≥1 strong concept, or ≥2 plain ones
                edges.append({"s": pids[i], "t": pids[j], "w": w, "kind": "sib", "via": sh})

    # paper → related library papers (top neighbours by shared specific concepts)
    used_lib = {}
    for pid, spec in paper_kw.items():
        cand = []
        for L in lib:
            w, sh = rel(spec, L["ek"])
            if w >= 2:
                cand.append((w, sh, L))
        cand.sort(key=lambda x: -x[0])
        for w, sh, L in cand[:6]:
            lid = "L:" + L["note"]
            if lid not in used_lib:
                larea = area_of_keywords(L["kws"])
                add(lid, label=clean_label(L["title"]), type="lib", area=larea,
                    detail={"title": L["title"], "kind": "in your library",
                            "note": L["note"], "colls": L["colls"]})
                used_lib[lid] = True
            edges.append({"s": pid, "t": lid, "w": w, "kind": "lib", "via": sh})

    # papers the user ADDED to Zotero today always show in today's graph —
    # what you saved today belongs in today's picture, even when no fetched
    # paper shares enough concepts to pull it in as a neighbour.
    for L in lib:
        if not date or L.get("added") != date:
            continue
        lid = "L:" + L["note"]
        if lid in used_lib:                       # already in — just flag it
            for n in nodes:
                if n["id"] == lid:
                    n["label"] = "📥 " + n["label"]
                    n["detail"]["kind"] = "📥 added to your library today"
            continue
        larea = area_of_keywords(L["kws"])
        aid = "A:" + larea
        add(aid, label="Other" if larea == "_other" else larea, type="area",
            area=larea, detail={"title": "Other" if larea == "_other" else larea,
                                "kind": "interest area"})
        add(lid, label="📥 " + clean_label(L["title"]), type="lib", area=larea,
            detail={"title": L["title"], "kind": "📥 added to your library today",
                    "note": L["note"], "colls": L["colls"]})
        used_lib[lid] = True
        edges.append({"s": lid, "t": aid, "w": 1, "kind": "area"})
        for pid, spec in paper_kw.items():        # weaker links allowed here
            w, sh = rel(spec, L["ek"])
            if w >= 1:
                edges.append({"s": pid, "t": lid, "w": w, "kind": "lib", "via": sh})
    return nodes, edges


def render_html(date, nodes, edges, live=False):
    data = json.dumps({"nodes": nodes, "edges": edges, "colors": AREA_COLOR,
                       "date": date, "live": live,
                       "questions": questions_payload(),
                       "inbox": inbox_backlog()}, ensure_ascii=False)
    return HTML_TEMPLATE.replace("__DATA__", data).replace("__DATE__", html.escape(date))


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Paper graph · __DATE__</title>
<script>window.MathJax={tex:{inlineMath:[['$','$'],['\\(','\\)']],displayMath:[['$$','$$'],['\\[','\\]']]},options:{ignoreHtmlClass:'nomath',skipHtmlTags:['script','style','textarea']}};</script>
<script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
<style>
  :root{--bg:#11131a;--panel:#1b1e28;--ink:#e8eaf0;--mut:#9aa0b4;--line:#2a2e3c;}
  *{box-sizing:border-box}
  body{margin:0;font:15px/1.6 -apple-system,Segoe UI,Roboto,Helvetica,Arial,"PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--ink);overflow:hidden}
  #wrap{display:flex;height:100vh;width:100vw}
  /* min-width:0 lets the canvas flex item shrink below its intrinsic (width-attr)
     size; without it the canvas overflows and pushes #side off-screen. */
  #cv{flex:1 1 0;min-width:0;display:block;cursor:grab}
  #side{width:540px;flex:none;background:var(--panel);border-right:1px solid var(--line);padding:22px 24px 56px;overflow:auto}
  #side h1{font-size:19px;margin:0 0 2px}
  #side .sub{color:var(--mut);font-size:13.5px;margin-bottom:18px}
  #side .empty{color:var(--mut);margin-top:30px;font-size:15px;line-height:1.7}
  .card h2{font-size:20px;margin:0 0 12px;line-height:1.45}
  .pill{display:inline-block;font-size:12.5px;padding:3px 9px;border-radius:20px;background:#272b39;color:var(--mut);margin:0 6px 6px 0}
  .sec{margin:15px 0}
  .sec .lab{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);margin-bottom:4px}
  .sec .val{font-size:15.5px;line-height:1.6}
  .abs{font-size:14px;line-height:1.6;color:#c6cad8;max-height:240px;overflow:auto;border-left:2px solid var(--line);padding-left:11px}
  a{color:#7fb3ff}
  .fb{display:flex;gap:8px;margin:14px 0 4px;flex-wrap:wrap}
  .fb button{flex:1;min-width:100px;cursor:pointer;border:1px solid var(--line);background:#222634;color:var(--ink);
    border-radius:9px;padding:10px 7px;font-size:14px;transition:.12s}
  .fb button:hover{border-color:#5566aa;background:#2a3042}
  .fb button.on{background:#2f6b46;border-color:#3ab07a}
  .fb button.off{background:#6b2f3a;border-color:#e6557a}
  .fb button.zo{background:#33406b;border-color:#5a6ad0}
  .fbmsg{font-size:13px;color:var(--mut);min-height:16px;margin-top:6px}
  .btnrow{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
  .deepbtn,.origbtn{cursor:pointer;border:1px solid #4a5275;background:#2b3354;color:#dfe4f5;border-radius:9px;padding:9px 12px;font-size:14px}
  .deepbtn:hover,.origbtn:hover{background:#34406b}
  .deepbtn:disabled{opacity:.6;cursor:default}
  .origbtn{border-color:#3a4258;background:#222634}
  .deepmsg{font-size:12.5px;color:var(--mut)}
  /* original reading pane: flex-grow to take most of the space right of #side,
     so text/figures are large and clear without zooming */
  #origpanel{flex:1 1 0;min-width:0;background:#0f1117;border-right:1px solid var(--line);overflow:hidden;padding:0}
  .pdfframe{width:100%;height:100vh;border:0;display:block;background:#fff}
  .origbody{max-width:1150px;margin:0 auto;font-size:16.5px;line-height:1.85;color:#d2d7e6;text-align:left}
  .origttl{font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.08em;margin-bottom:16px;position:sticky;top:-26px;background:#0f1117;padding:10px 0;z-index:2;max-width:1150px;margin-left:auto;margin-right:auto}
  .origbody p{margin:13px 0}
  .origbody dl{margin:10px 0}.origbody dt{font-weight:650;color:#fff;margin-top:8px}.origbody dd{margin:2px 0 8px}
  .origbody h1,.origbody h2,.origbody h3,.origbody h4{color:#fff;line-height:1.35;margin:26px 0 10px;font-weight:650}
  .origbody h1{font-size:25px}.origbody h2{font-size:21px}.origbody h3{font-size:18px}.origbody h4{font-size:16.5px}
  .origbody img{max-width:100%;height:auto;display:block;margin:18px auto;background:#fff;border-radius:8px;padding:10px}
  .origbody figure{margin:22px 0;text-align:left}
  .origbody .ltx_listing,.origbody .ltx_algorithm{text-align:left}
  .origbody figcaption{font-size:14px;color:var(--mut);margin-top:8px;line-height:1.5}
  .origbody table{border-collapse:collapse;margin:18px 0;font-size:14px;max-width:100%;overflow:auto;display:block}
  .origbody td,.origbody th{border:1px solid #333a4d;padding:6px 10px}
  .origbody th{background:#1b1f2b}
  .origbody ul,.origbody ol{padding-left:24px;margin:10px 0}
  .origbody li{margin:5px 0}
  .origbody cite{color:#9fb0d8;font-style:normal}
  /* algorithms → framed code block */
  .origbody .ltx_float_algorithm{border:1px solid #39414f;background:#0b0d14;border-radius:10px;padding:14px 18px;margin:20px 0}
  .origbody .ltx_float_algorithm figcaption{font-weight:650;color:#fff;margin-bottom:8px;border-bottom:1px solid #2a3140;padding-bottom:6px}
  .origbody .ltx_listingline{display:block;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:14px;line-height:1.75;white-space:pre-wrap;padding:1px 0;color:#d7dcec}
  .origbody .ltx_listing_data{display:none}
  /* bigger, legible math */
  .origbody mjx-container{font-size:1.2em!important}
  .origbody mjx-container[display="true"]{font-size:1.32em!important;overflow-x:auto;overflow-y:hidden;max-width:100%}
  .md mjx-container{font-size:1.1em!important}
  .md mjx-container[display="true"]{font-size:1.18em!important;overflow-x:auto;overflow-y:hidden}
  .md{font-size:14px;line-height:1.65;color:#dde1ee}
  .md .mdh{font-weight:600;color:#fff;margin:14px 0 4px;font-size:14.5px}
  .md p{margin:6px 0}
  .md ul{margin:6px 0 6px 4px;padding-left:18px}
  .md li{margin:3px 0}
  .md code{background:#272b39;padding:1px 5px;border-radius:4px;font-size:13px}
  .md .mdt{border-collapse:collapse;margin:8px 0;width:100%;font-size:13px}
  .md .mdt th,.md .mdt td{border:1px solid var(--line);padding:5px 8px;text-align:left;vertical-align:top}
  .md .mdt th{background:#272b39}
  .md .mathblock{overflow-x:auto;margin:8px 0}
  /* library search + note reading (Obsidian-in-the-web) */
  .libsearch{width:100%;box-sizing:border-box;margin:0 0 14px;padding:10px 13px;font-size:14px;
    border:1px solid var(--line);border-radius:9px;background:#15171f;color:var(--ink)}
  .libsearch:focus{outline:none;border-color:#5566aa}
  .result{padding:9px 11px;border-radius:8px;cursor:pointer;border:1px solid transparent;margin:2px 0}
  .result:hover{background:#222634;border-color:var(--line)}
  .result .rt{font-size:14px;color:#e3e7f2;line-height:1.35}
  .result .rm{font-size:12px;color:var(--mut);margin-top:3px}
  .reshead{font-size:12px;color:var(--mut);margin:2px 0 8px}
  .note blockquote{border-left:3px solid #3a4258;margin:9px 0;padding:5px 0 5px 13px;color:#c1c7d8;font-size:13.5px}
  .note .wl,.md .wl{color:#7fb3ff;cursor:pointer;border-bottom:1px dotted #4a5578}
  .note .wl:hover,.md .wl:hover{color:#aecbff}
  .notearea{width:100%;box-sizing:border-box;min-height:200px;resize:vertical;
    font:13.5px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
    background:#15171f;color:#dde1ee;border:1px solid var(--line);border-radius:8px;padding:11px}
  .notearea:focus{outline:none;border-color:#5566aa}
  .hinttxt{font-size:12.5px;color:var(--mut);margin:4px 0 8px;line-height:1.6}
  /* open questions / ideas radar panel */
  .qopen{width:100%;margin:0 0 14px;padding:10px 13px;font-size:14px;cursor:pointer;text-align:left;
    border:1px solid var(--line);border-radius:9px;background:#222634;color:var(--ink)}
  .qopen:hover{border-color:#5566aa;background:#2a3042}
  .qopen span{color:var(--mut);font-size:12.5px}
  .qcard{border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:12px 0;background:#171a23}
  .qcard h3{font-size:15.5px;margin:0 0 7px;line-height:1.45}
  .qbody{font-size:13.5px;color:#c1c7d8;white-space:pre-wrap;max-height:130px;overflow:auto;margin-bottom:7px}
  .qhits{padding-left:18px;font-size:13.5px;margin:6px 0}
  .qhits li{margin:7px 0;line-height:1.55}
  .qnone{color:var(--mut);font-size:13px}
  .qsolve{cursor:pointer;background:none;border:1px solid var(--line);border-radius:6px;color:var(--mut);font-size:12px;padding:2px 7px;margin-left:6px;vertical-align:2px}
  .qsolve:hover{border-color:#3ab07a;color:#3ab07a}
  .qform input.libsearch{margin-bottom:8px}
  .starrow{display:flex;align-items:center;gap:2px}
  .starrow .star{cursor:pointer;font-size:22px;line-height:1;color:#3a4258;transition:.1s}
  .starrow .star.on{color:#f5c542}
  .starrow .star:hover{transform:scale(1.15)}
  .starrow .deepmsg{margin-left:9px}
  .ibrow{padding:9px 12px;border:1px solid var(--line);border-radius:9px;margin:8px 0;cursor:pointer}
  .ibrow:hover{background:#222634}
  .ibrow .rt{font-size:14px;color:#e3e7f2;line-height:1.4}
  .ibrow .rm{font-size:12px;color:var(--mut);margin-top:3px}
  #qathread{max-height:340px;overflow:auto}
  .qaq{font-size:13.5px;color:#dfe4f5;background:#222a40;border-radius:9px;padding:7px 11px;margin:9px 0 5px}
  .qaa{border-left:2px solid #3ab07a;padding:2px 0 2px 11px;margin:0 0 6px}
  .legend{position:fixed;right:14px;top:12px;background:rgba(27,30,40,.85);border:1px solid var(--line);border-radius:10px;padding:10px 12px;font-size:12px}
  .legend .row{display:flex;align-items:center;margin:3px 0}
  .legend .dot{width:11px;height:11px;border-radius:50%;margin-right:7px;flex:none}
  .hint{position:fixed;right:14px;bottom:12px;color:var(--mut);font-size:11px}
</style></head>
<body>
<div id="wrap">
  <div id="side"><h1>Today's recommendations</h1><div class="sub">__DATE__ · click a node, or search your library ↓</div>
    <input id="libsearch" class="libsearch" type="search" placeholder="🔎 Search your library — title, abstract, your highlights…" autocomplete="off">
    <button class="qopen" onclick="showQuestions()">❓ 问题与想法 · 雷达 <span id="qbadge"></span></button>
    <button class="qopen" onclick="showInbox()">📥 未处理的推荐 <span id="ibadge"></span></button>
    <div id="detail"><div class="empty">Click a paper node (solid dot) for its value card; click a library paper (ring) to read its note + your highlights; or search above.</div></div>
  </div>
  <div id="origpanel" style="display:none"></div>
  <canvas id="cv"></canvas>
</div>
<div class="legend" id="legend"></div>
<div class="hint">click a node for details · drag canvas to pan · scroll to zoom · drag a node to pull it · edges = shared concepts</div>
<script>
const DATA = __DATA__;
const LIVE = DATA.live && location.protocol==='http:';
const cv=document.getElementById('cv'),ctx=cv.getContext('2d');
const colors=DATA.colors;
let W,H,DPR;
let dirty=true;   // draw only when something changed — an idle graph must not
                  // burn 60fps (it made typing in the note editor laggy)
function resize(){DPR=devicePixelRatio||1;W=cv.clientWidth;H=cv.clientHeight;cv.width=W*DPR;cv.height=H*DPR;ctx.setTransform(DPR,0,0,DPR,0,0);dirty=true;}
window.addEventListener('resize',resize);resize();

const N=DATA.nodes.map((n,i)=>({...n,
  x:W/2+Math.cos(i*2.4)*(120+i*9),y:H/2+Math.sin(i*2.4)*(120+i*9),vx:0,vy:0,
  r:n.type==='area'?16:(n.type==='paper'?11:7)}));
const idx=Object.fromEntries(N.map((n,i)=>[n.id,i]));
const ZORD={area:0,lib:1,paper:2};                       // paint order: papers on top
const DRAW=[...N].sort((a,b)=>ZORD[a.type]-ZORD[b.type]);
const E=DATA.edges.map(e=>({s:idx[e.s],t:idx[e.t],w:e.w||1,kind:e.kind})).filter(e=>e.s!=null&&e.t!=null);
const adj={};E.forEach(e=>{(adj[e.s]=adj[e.s]||new Set()).add(e.t);(adj[e.t]=adj[e.t]||new Set()).add(e.s);});

let view={x:0,y:0,k:1.4},sel=null,hover=null,drag=null,pan=null,moved=0,alpha=1,userMoved=false;
function reheat(a){alpha=Math.max(alpha,a);dirty=true;}
function fitView(){   // center the MAIN cluster and zoom to fit, until the user takes control.
  // Robust to outliers: a couple of weakly-linked nodes flung far out must not
  // drive the camera (they shoved the cluster into a corner).
  const k=view.k||1;
  const xs=N.map(n=>n.x).sort((p,q)=>p-q),ys=N.map(n=>n.y).sort((p,q)=>p-q);
  const mx=xs[xs.length>>1],my=ys[ys.length>>1];
  const ds=N.map(n=>Math.hypot(n.x-mx,n.y-my)).sort((p,q)=>p-q);
  const lim=Math.max(ds[(ds.length*0.85)|0]*1.6,260);
  let a=1e9,b=1e9,c=-1e9,d=-1e9;
  for(const n of N){
    if(Math.hypot(n.x-mx,n.y-my)>lim)continue;
    const rr=n.r/k;
    const lw=(Math.min(n.label.length,46)*6.6+n.r+10)/k;  // label extends to the right
    if(n.x-rr<a)a=n.x-rr; if(n.x+lw>c)c=n.x+lw;
    if(n.y-rr<b)b=n.y-rr; if(n.y+rr>d)d=n.y+rr;}
  if(a>c)return;
  const bw=(c-a)||1,bh=(d-b)||1,pad=Math.min(W,H)*0.10;
  view.k=Math.max(0.4,Math.min(2.6,Math.min((W-pad)/bw,(H-pad)/bh)));
  view.x=-((a+c)/2-W/2)*view.k;
  view.y=-((b+d)/2-H/2)*view.k;
}
function col(n){return colors[n.area]||colors['_other'];}
function step(){
  for(const n of N){n.vx*=0.85;n.vy*=0.85;}
  for(let i=0;i<N.length;i++)for(let j=i+1;j<N.length;j++){
    const a=N[i],b=N[j];let dx=a.x-b.x,dy=a.y-b.y,d2=dx*dx+dy*dy||1;
    if(d2<160000){const d=Math.sqrt(d2),f=3200/d2;a.vx+=dx/d*f;a.vy+=dy/d*f;b.vx-=dx/d*f;b.vy-=dy/d*f;}
  }
  for(const e of E){const a=N[e.s],b=N[e.t];let dx=b.x-a.x,dy=b.y-a.y,d=Math.sqrt(dx*dx+dy*dy)||1;
    const target=(a.type==='area'||b.type==='area')?180:100;const f=(d-target)*0.014*Math.min(2,e.w/2+.5);
    a.vx+=dx/d*f;a.vy+=dy/d*f;b.vx-=dx/d*f;b.vy-=dy/d*f;}
  for(const n of N){n.vx+=(W/2-n.x)*0.001;n.vy+=(H/2-n.y)*0.001;if(n!==drag){n.x+=n.vx;n.y+=n.vy;}}
}
function T(n){return{x:(n.x-W/2)*view.k+W/2+view.x,y:(n.y-H/2)*view.k+H/2+view.y};}
function inv(mx,my){return{x:(mx-W/2-view.x)/view.k+W/2,y:(my-H/2-view.y)/view.k+H/2};}
// multi-layer parallax starfield (live twinkle + slow drift)
const STARS=Array.from({length:520},()=>{const z=Math.random();return{x:Math.random(),y:Math.random(),
  r:(z*z)*1.9+0.25,t:Math.random()*6.28,sp:0.3+Math.random()*1.8,dx:(z*0.004+0.0006)*(Math.random()<.5?-1:1),
  hue:Math.random()<0.22?'#bcd2ff':(Math.random()<0.45?'#ffe3bf':'#ffffff'),br:0.25+z*0.7};});
// pre-render a rich face-on galaxy once to an offscreen canvas (additive glow)
function buildGalaxy(){
  const S=1024,oc=document.createElement('canvas');oc.width=S;oc.height=S;
  const o=oc.getContext('2d'),cx=S/2,cy=S/2;o.globalCompositeOperation='lighter';
  const NEB=['rgba(72,40,150,','rgba(28,86,168,','rgba(168,42,120,','rgba(36,128,150,'];
  for(let i=0;i<30;i++){const ang=Math.random()*6.28,rad=Math.pow(Math.random(),.5)*S*0.42;
    const x=cx+Math.cos(ang)*rad,y=cy+Math.sin(ang)*rad,r=S*(0.05+Math.random()*0.16),c=NEB[i%NEB.length];
    const g=o.createRadialGradient(x,y,0,x,y,r);g.addColorStop(0,c+(0.05+Math.random()*0.06).toFixed(3)+')');g.addColorStop(1,c+'0)');
    o.fillStyle=g;o.beginPath();o.arc(x,y,r,0,7);o.fill();}
  const ARMS=4;
  for(let i=0;i<6000;i++){
    const t=Math.pow(Math.random(),0.5),arm=Math.floor(Math.random()*ARMS);
    const ang=arm*(6.2832/ARMS)+t*5.2+(Math.random()-0.5)*((1-t)*1.1+0.12);
    const rad=t*S*0.47,x=cx+Math.cos(ang)*rad,y=cy+Math.sin(ang)*rad;
    let col;if(t<0.16)col='rgba(210,226,255,';else if(t<0.46)col='rgba(255,'+(222+(Math.random()*30|0))+','+(186+(Math.random()*46|0))+',';
    else col='rgba(255,'+(150+(Math.random()*70|0))+','+(168+(Math.random()*64|0))+',';
    const a=(0.5*(1-t)+0.07)*(0.45+Math.random()*0.55),r=Math.random()<0.07?(1.3+Math.random()*1.8):(0.5+Math.random()*0.85);
    o.fillStyle=col+a.toFixed(3)+')';o.beginPath();o.arc(x,y,r,0,7);o.fill();}
  // dust lanes: carve faint dark arcs
  o.globalCompositeOperation='destination-out';
  for(let i=0;i<3;i++){o.save();o.translate(cx,cy);o.rotate(i*2.1);o.scale(1,0.34);
    o.strokeStyle='rgba(0,0,0,0.5)';o.lineWidth=S*0.018;o.beginPath();
    for(let a=0;a<6.0;a+=0.05){const rr=S*0.05*Math.exp(0.26*a);if(rr>S*0.46)break;o.lineTo(Math.cos(a)*rr,Math.sin(a)*rr);}o.stroke();o.restore();}
  // core glow (kept soft so it doesn't blow out the scene)
  o.globalCompositeOperation='lighter';
  const cg=o.createRadialGradient(cx,cy,0,cx,cy,S*0.13);
  cg.addColorStop(0,'rgba(255,250,238,0.55)');cg.addColorStop(0.4,'rgba(255,230,198,0.22)');cg.addColorStop(1,'rgba(255,205,150,0)');
  o.fillStyle=cg;o.beginPath();o.arc(cx,cy,S*0.13,0,7);o.fill();
  return oc;
}
let GALIMG=null;
const T0=performance.now();let shoot=null;
function drawBG(){
  const tm=(performance.now()-T0)/1000;
  let g=ctx.createLinearGradient(0,0,0,H);
  g.addColorStop(0,'#06050f');g.addColorStop(0.55,'#080614');g.addColorStop(1,'#040309');
  ctx.fillStyle=g;ctx.fillRect(0,0,W,H);
  // galaxy (fixed tilt, slow spin), additive — offset to a side so it never sits
  // behind the node cluster (which lives at screen center)
  if(!GALIMG)GALIMG=buildGalaxy();
  const s=Math.min(W,H)*1.5;
  ctx.save();ctx.globalCompositeOperation='lighter';
  ctx.translate(W*0.5,H*0.5);ctx.scale(1,0.5);ctx.rotate(tm*0.016);
  ctx.globalAlpha=0.42+0.05*Math.sin(tm*0.35);
  ctx.drawImage(GALIMG,-s/2,-s/2,s,s);ctx.restore();
  ctx.globalAlpha=1;ctx.globalCompositeOperation='source-over';
  // parallax stars on top
  ctx.globalCompositeOperation='lighter';
  for(const st of STARS){const al=st.br*(0.45+0.55*Math.abs(Math.sin(tm*st.sp+st.t)));
    let x=(st.x+st.dx*tm)%1;if(x<0)x+=1;
    ctx.globalAlpha=al;ctx.fillStyle=st.hue;ctx.beginPath();ctx.arc(x*W,st.y*H,st.r,0,7);ctx.fill();
    if(st.r>1.4){ctx.globalAlpha=al*0.5;ctx.beginPath();ctx.arc(x*W,st.y*H,st.r*0.4,0,7);ctx.fillStyle='#fff';ctx.fill();}}
  ctx.globalAlpha=1;ctx.globalCompositeOperation='source-over';
  // shooting star
  if(!shoot&&Math.random()<0.005)shoot={x:Math.random()*W*0.7,y:Math.random()*H*0.4,vx:8+Math.random()*7,vy:3+Math.random()*3,life:0};
  if(shoot){shoot.x+=shoot.vx;shoot.y+=shoot.vy;shoot.life++;
    const gx=ctx.createLinearGradient(shoot.x,shoot.y,shoot.x-shoot.vx*10,shoot.y-shoot.vy*10);
    gx.addColorStop(0,'rgba(255,255,255,0.95)');gx.addColorStop(1,'rgba(255,255,255,0)');
    ctx.strokeStyle=gx;ctx.lineWidth=2;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(shoot.x,shoot.y);ctx.lineTo(shoot.x-shoot.vx*10,shoot.y-shoot.vy*10);ctx.stroke();
    if(shoot.life>60||shoot.x>W+40||shoot.y>H+40)shoot=null;}
  // cinematic vignette
  const vg=ctx.createRadialGradient(W/2,H/2,Math.min(W,H)*0.35,W/2,H/2,Math.max(W,H)*0.75);
  vg.addColorStop(0,'rgba(0,0,0,0)');vg.addColorStop(1,'rgba(0,0,0,0.55)');
  ctx.fillStyle=vg;ctx.fillRect(0,0,W,H);
}
function draw(){
  drawBG();
  for(const e of E){const a=T(N[e.s]),b=T(N[e.t]);
    const hot=sel&&(N[e.s]===sel||N[e.t]===sel);
    ctx.strokeStyle=hot?'rgba(180,200,255,.6)':(e.kind==='lib'?'rgba(150,140,200,.16)':'rgba(140,150,180,.12)');
    ctx.lineWidth=hot?Math.min(3,e.w*0.5):Math.min(2,e.w*0.3);
    ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();}
  for(const n of DRAW){const p=T(n),r=n.r*view.k;
    const dim=sel&&n!==sel&&!(adj[idx[n.id]]&&adj[idx[n.id]].has(idx[sel.id]));
    ctx.globalAlpha=dim?0.22:1;
    ctx.beginPath();ctx.arc(p.x,p.y,r,0,7);
    if(n.type==='lib'){              // library papers = hollow ring
      ctx.fillStyle='#11131a';ctx.fill();
      ctx.lineWidth=2;ctx.strokeStyle=col(n);ctx.stroke();
    }else if(n.type==='area'){       // interest area = solid disc + halo
      ctx.fillStyle=col(n);ctx.fill();
      ctx.globalAlpha=dim?0.1:0.18;ctx.beginPath();ctx.arc(p.x,p.y,r+6,0,7);ctx.fillStyle=col(n);ctx.fill();
    }else{                           // today's recommended paper = solid dot
      ctx.fillStyle=col(n);ctx.fill();
    }
    ctx.globalAlpha=dim?0.4:1;
    if(n===sel||n===hover){ctx.lineWidth=2.5;ctx.strokeStyle='#fff';ctx.stroke();}
    ctx.globalAlpha=1;
    if(n.type==='area'||n===sel||n===hover||view.k>1.3){
      ctx.globalAlpha=dim?0.4:1;
      ctx.font=(n.type==='area'?'600 13px':'12px')+' sans-serif';
      const lab=n.label.length>46?n.label.slice(0,44)+'…':n.label;
      ctx.lineWidth=3.5;ctx.strokeStyle='rgba(0,0,0,0.82)';ctx.lineJoin='round';
      ctx.strokeText(lab,p.x+r+4,p.y+4);                 // dark outline for legibility
      ctx.fillStyle=n.type==='area'?'#fff':'#e3e7f2';
      ctx.fillText(lab,p.x+r+4,p.y+4);ctx.globalAlpha=1;}
  }
}
function loop(){
  if(alpha>0.02||drag){step();alpha*=0.98;dirty=true;}
  if(!userMoved){const k0=view.k,x0=view.x,y0=view.y;fitView();
    if(Math.abs(view.k-k0)>1e-4||Math.abs(view.x-x0)>0.3||Math.abs(view.y-y0)>0.3)dirty=true;}
  if(dirty){draw();dirty=false;}
  requestAnimationFrame(loop);}
function pick(mx,my){let best=null,bd=1e9,bp=-1;for(const n of N){const p=T(n),dx=p.x-mx,dy=p.y-my,d=dx*dx+dy*dy;
  const hit=(n.r*view.k+12)**2;if(d<hit){const pr=ZORD[n.type]||0;
    if(pr>bp||(pr===bp&&d<bd)){bp=pr;bd=d;best=n;}}}return best;}
function xy(e){const r=cv.getBoundingClientRect();return {x:e.clientX-r.left,y:e.clientY-r.top};}
function onDown(e){const m=xy(e);moved=0;const n=pick(m.x,m.y);
  if(n){drag=n;reheat(0.25);}else{pan={x:m.x-view.x,y:m.y-view.y};cv.style.cursor='grabbing';userMoved=true;}}
function onMove(e){const m=xy(e);
  if(drag){moved++;if(moved>3)userMoved=true;const w=inv(m.x,m.y);drag.x=w.x;drag.y=w.y;drag.vx=drag.vy=0;}
  else if(pan){moved++;view.x=m.x-pan.x;view.y=m.y-pan.y;dirty=true;}
  else{const h=pick(m.x,m.y);if(h!==hover){hover=h;dirty=true;}cv.style.cursor=hover?'pointer':'grab';}}
function onUp(e){const m=xy(e);const n=pick(m.x,m.y);
  if(n&&moved<6)select(n);
  drag=null;pan=null;cv.style.cursor='grab';}
// Pointer events cover mouse + trackpad + touch and are the most reliable.
if(window.PointerEvent){
  cv.addEventListener('pointerdown',e=>{cv.setPointerCapture&&cv.setPointerCapture(e.pointerId);onDown(e);});
  cv.addEventListener('pointermove',onMove);
  cv.addEventListener('pointerup',onUp);
}else{
  cv.addEventListener('mousedown',onDown);window.addEventListener('mousemove',onMove);window.addEventListener('mouseup',onUp);
}
cv.addEventListener('wheel',e=>{e.preventDefault();userMoved=true;const f=e.deltaY<0?1.12:0.89;view.k=Math.max(0.3,Math.min(4,view.k*f));reheat(0.05);},{passive:false});

function esc(s){return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function sec(l,v){return v?`<div class="sec"><div class="lab">${l}</div><div class="val">${esc(v)}</div></div>`:'';}
function select(n){sel=n;dirty=true;window._lastView={kind:'node',n:n};
  const el0=document.getElementById('detail');el0.dataset.qopen='';el0.dataset.iopen='';
  const d=n.detail||{},el=el0;
  if(n.type==='area'){el.innerHTML=`<div class="card"><h2>${esc(d.title)}</h2><span class="pill">interest area</span>
    <div class="sec"><div class="val">Papers and library notes linked here share concepts in this area of yours. Click them to compare.</div></div></div>`;return;}
  if(n.type==='lib'){openNote(d.note||n.id.slice(2));return;}
  const pills=(d.matched||[]).map(m=>`<span class="pill">${esc(m)}</span>`).join('');
  let fb='';
  if(d.arxiv){fb=`<div class="fb" data-id="${esc(d.arxiv)}">
    <button class="on" onclick="fb('${esc(d.arxiv)}','keep',this)">👍 More like this</button>
    <button class="off" onclick="fb('${esc(d.arxiv)}','drop',this)">👎 Less</button>
    <button class="zo" onclick="fb('${esc(d.arxiv)}','add',this)">➕ Zotero + PDF</button>
  </div><div class="fbmsg" id="fbmsg">${LIVE?'':'(run <code>viz.py --serve</code> for live buttons)'}</div>`;}
  const op=document.getElementById('origpanel');const origOpen=op&&op.style.display==='block';
  let btns='';
  if(d.arxiv){btns=`<div class="sec btnrow">
    <button class="deepbtn" onclick="deepread('${esc(d.arxiv)}',this)">🔬 ${d.deep?'Regenerate':'Generate'} deep read (full text)</button>
    <button class="origbtn" onclick="toggleOrig('${esc(d.arxiv)}',this)">📄 ${origOpen?'Hide':'Show'} original →</button>
    <button class="origbtn" onclick="toggleQA('${esc(d.arxiv)}')">💬 提问</button>
    <button class="origbtn" onclick="editStub('${esc(d.arxiv)}')">✍️ 写笔记</button>
    <span class="deepmsg" id="deepmsg"></span></div>`;}
  const deepBox=`<div class="deepwrap" id="deepwrap">${d.deep?`<div class="sec"><div class="lab">Deep read (method analysis)</div><div class="md" id="deepmd"></div></div>`:''}</div>`;
  el.innerHTML=`<div class="card"><h2>${esc(d.title)}</h2>
    <span class="pill">${esc(d.source||'')}</span><span class="pill">score ${d.score}</span>
    ${d.url?`<span class="pill"><a href="${d.url}" target="_blank">arXiv ↗</a></span>`:''}
    <div style="margin:6px 0">${pills}</div>
    ${sec('Problem',d.problem)}${sec('Innovation',d.innovation)}${sec('Potential directions',d.directions)}
    ${(d.problem||d.innovation||d.directions)?'':'<div class="sec"><div class="val" style="color:var(--mut)">No value card yet — run <code>/papers digest</code>.</div></div>'}
    ${btns}<div id="qabox"></div><div id="noteedit"></div>${deepBox}
    ${d.abstract?`<div class="sec"><div class="lab">Abstract</div><div class="abs">${esc(d.abstract)}</div></div>`:''}
    ${fb}</div>`;
  if(d.deep){const md=document.getElementById('deepmd');if(md)md.innerHTML=md2html(d.deep);}
  typeset(el);   // typeset the whole card: title, abstract, value cards, deep read
  if(origOpen&&d.arxiv)loadOrig(d.arxiv);}
function typeset(el){if(window.MathJax&&MathJax.typesetPromise)MathJax.typesetPromise([el]).catch(()=>{});}
function md2html(s){
  const e=x=>x.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
  const inl=t=>e(t).replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>').replace(/`(.+?)`/g,'<code>$1</code>')
    .replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g,(m,a,b)=>`<span class="wl" data-note="${a.trim()}">${(b||a).trim()}</span>`)
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,'<a href="$2" target="_blank">$1</a>');
  const L=s.replace(/\r/g,'').split('\n');let o=[],i=0;
  while(i<L.length){let ln=L[i];
    if(ln.trim().startsWith('$$')){  // display math (pass raw to MathJax, may span lines)
      let buf=ln;
      if((ln.match(/\$\$/g)||[]).length>=2){o.push(`<div class="mathblock">${buf}</div>`);i++;continue;}
      i++;while(i<L.length){buf+='\n'+L[i];const done=L[i].includes('$$');i++;if(done)break;}
      o.push(`<div class="mathblock">${buf}</div>`);continue;}
    if(/^\s*\|.*\|/.test(ln)){let tb=[];while(i<L.length&&/^\s*\|.*\|/.test(L[i])){tb.push(L[i]);i++;}
      tb=tb.filter(r=>!/^\s*\|[\s:|-]+\|\s*$/.test(r));
      o.push('<table class="mdt">'+tb.map((r,ri)=>{const c=r.trim().replace(/^\|/,'').replace(/\|$/,'').split('|').map(x=>x.trim());
        const tg=ri===0?'th':'td';return '<tr>'+c.map(x=>`<${tg}>${inl(x)}</${tg}>`).join('')+'</tr>';}).join('')+'</table>');continue;}
    let h=ln.match(/^(#{1,4})\s+(.*)/);if(h){o.push(`<div class="mdh">${inl(h[2])}</div>`);i++;continue;}
    if(/^\s*[-*]\s+/.test(ln)){let li=[];while(i<L.length&&/^\s*[-*]\s+/.test(L[i])){li.push(L[i].replace(/^\s*[-*]\s+/,''));i++;}
      o.push('<ul>'+li.map(x=>`<li>${inl(x)}</li>`).join('')+'</ul>');continue;}
    if(/^\s*>/.test(ln)){let q=[];while(i<L.length&&/^\s*>/.test(L[i])){q.push(L[i].replace(/^\s*>\s?/,''));i++;}
      o.push('<blockquote>'+q.map(x=>x.trim()===''?'':inl(x)).join('<br>')+'</blockquote>');continue;}
    if(ln.trim()===''){i++;continue;}o.push(`<p>${inl(ln)}</p>`);i++;}
  return o.join('');}
window.deepread=function(id,btn){
  const msg=document.getElementById('deepmsg');
  if(!LIVE){msg.textContent=' — needs viz.py --serve';return;}
  btn.disabled=true;msg.textContent=' generating… (reads the PDF, ~30–90s)';
  fetch('/deepread',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})})
    .then(r=>r.json()).then(j=>{btn.disabled=false;
      if(j.ok){msg.textContent=' ✓ done';const w=document.getElementById('deepwrap');
        w.innerHTML=`<div class="sec"><div class="lab">Deep read (method analysis)</div><div class="md" id="deepmd">${md2html(j.deep)}</div></div>`;
        typeset(document.getElementById('deepmd'));
        btn.textContent='🔬 Regenerate deep read (full text)';}
      else{msg.textContent=' ⚠ '+(j.msg||'failed');}
    }).catch(e=>{btn.disabled=false;msg.textContent=' ⚠ '+e;});
};
function loadOrig(id){
  const p=document.getElementById('origpanel');
  if(p.dataset.loaded===id){return;}
  p.dataset.loaded=id;
  if(!LIVE){p.innerHTML='<div style="padding:20px;color:var(--mut)">(needs viz.py --serve to load the PDF)</div>';return;}
  // embed the real arXiv PDF (proxied via our local server) — native rendering
  p.innerHTML=`<iframe class="pdfframe" src="/pdf?id=${encodeURIComponent(id)}#view=FitH" title="paper PDF"></iframe>`;
}
window.toggleOrig=function(id,btn){
  const p=document.getElementById('origpanel');
  if(p.style.display==='block'){
    p.style.display='none';cv.style.display='block';resize();btn.textContent='📄 Show original →';return;}
  p.style.display='block';cv.style.display='none';   // hide graph → original gets full width
  btn.textContent='📄 Hide original';loadOrig(id);
  const qb=document.getElementById('qabox');          // reading mode → offer Q&A
  if(qb&&qb.dataset.open!=='1')toggleQA(id);
};
window.fb=function(id,verdict,btn){
  const msg=document.getElementById('fbmsg');
  if(!LIVE){msg.innerHTML=`would <b>${verdict}</b> ${id} — start <code>viz.py --serve</code> to record`;return;}
  msg.textContent='…';
  fetch('/feedback',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id,verdict})}).then(r=>r.json()).then(j=>{
      msg.innerHTML=j.ok?('✓ '+esc(j.msg||verdict)):('⚠ '+esc(j.msg||'failed'));
      if(j.ok&&btn){[...btn.parentNode.children].forEach(b=>b.style.opacity=.5);btn.style.opacity=1;}
    }).catch(e=>{msg.textContent='⚠ '+e;});
};
// ---- open questions / ideas radar panel (Research/questions.md + radar.md) ----
let QS=DATA.questions||[];
function qbadge(){const h=QS.reduce((a,t)=>a+(t.hits||[]).length,0);
  const b=document.getElementById('qbadge');if(b)b.textContent=`${QS.filter(t=>t.kind==='question').length} 问题 · ${h} 命中`;}
qbadge();
function relIcon(r){return ({'同问题':'🎯','组件':'🧩','撞车':'⚠️','旁证':'📎'})[r]||'📡';}
window.closeQuestions=function(){
  const el=document.getElementById('detail');el.dataset.qopen='';el.dataset.iopen='';
  const v=window._lastView;
  if(v&&v.kind==='node'){select(v.n);return;}
  if(v&&v.kind==='note'){openNote(v.slug);return;}
  el.innerHTML='<div class="empty">Click a paper node (solid dot) for its value card; click a library paper (ring) to read its note + your highlights; or search above.</div>';};
window.showQuestions=function(){
  const el0=document.getElementById('detail');
  if(el0.dataset.qopen==='1'){closeQuestions();return;}   // sidebar button = toggle
  renderQuestions();};
window.renderQuestions=function(){
  sel=null;dirty=true;const el=document.getElementById('detail');el.dataset.qopen='1';el.dataset.iopen='';
  const form=`<div class="qform">
    <input id="qtitle" class="libsearch" placeholder="新问题：一句话标题，如「触觉如何融入 VLA 的动作表征？」">
    <textarea id="qbody" class="notearea" style="min-height:84px" placeholder="背景 / 为什么难 / 你的直觉…（写得越具体，雷达匹配越准）"></textarea>
    <div class="btnrow" style="margin-top:8px">
      <button class="deepbtn" onclick="qadd(this)">➕ 记录问题</button>
      <button class="origbtn" onclick="qmatch(this)">📡 立即匹配今天的论文</button></div>
    <div class="fbmsg" id="qmsg">${LIVE?'':'(静态页只读 — 运行 <code>viz.py --serve</code> 可新增/匹配/标记)'}</div></div>`;
  const cards=QS.map(t=>{
    const hs=(t.hits||[]).map(h=>`<li>${relIcon(h.relation)} <b>${esc(h.relation)}</b> · <a href="${esc(h.url)}" target="_blank">${esc(h.title)}</a> <span style="color:var(--mut)">(${esc(h.date)})</span><br><span style="color:#aab1c6">${esc(h.why)}</span></li>`).join('');
    const solve=(LIVE&&t.kind==='question')?`<button class="qsolve" onclick="qsolve('${t.id}')" title="标记已解决，雷达不再匹配">✅ 已解决</button>`:'';
    return `<div class="qcard"><h3>${t.kind==='idea'?'💡':'❓'} ${esc(t.title)}${solve}</h3>
      ${t.text?`<div class="qbody">${esc(t.text)}</div>`:''}
      ${hs?`<ul class="qhits">${hs}</ul>`:'<div class="qnone">📡 还没有命中 — 每天 fetch 后自动匹配</div>'}</div>`;}).join('');
  el.innerHTML=`<div class="card"><h2>❓ 开放问题与想法 <button class="qsolve" style="float:right" onclick="closeQuestions()">✕ 返回</button></h2>
    <div class="hinttxt">记录你关心但还没解决的问题（存在 <code>Research/questions.md</code>，Obsidian 里也能改）。每天的新论文自动与之匹配：🎯同问题 · 🧩组件 · ⚠️撞车 · 📎旁证；命中也累积在 <code>Research/radar.md</code>。💡 来自 <code>Research/ideas/</code>。</div>
    ${form}${cards||'<div class="qnone" style="margin-top:14px">还没有问题 — 在上面写下第一个。</div>'}</div>`;
  typeset(el);};
window.qadd=function(btn){
  const msg=document.getElementById('qmsg');
  if(!LIVE){msg.innerHTML='需要 <code>viz.py --serve</code>';return;}
  const title=document.getElementById('qtitle').value.trim();
  const body=document.getElementById('qbody').value.trim();
  if(!title){msg.textContent='⚠ 先写一句话标题';return;}
  btn.disabled=true;msg.textContent='…';
  fetch('/qadd',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,body})})
    .then(r=>r.json()).then(j=>{btn.disabled=false;
      if(j.ok){QS=j.questions||QS;qbadge();renderQuestions();
        document.getElementById('qmsg').textContent='✓ '+(j.msg||'已记录')+' — 可点「📡 立即匹配」';}
      else msg.textContent='⚠ '+(j.msg||'failed');})
    .catch(e=>{btn.disabled=false;msg.textContent='⚠ '+e;});};
window.qmatch=function(btn){
  const msg=document.getElementById('qmsg');
  if(!LIVE){msg.innerHTML='需要 <code>viz.py --serve</code>';return;}
  btn.disabled=true;msg.textContent='📡 匹配中…（LLM 判断，约 1 分钟）';
  fetch('/qmatch',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})
    .then(r=>r.json()).then(j=>{QS=j.questions||QS;qbadge();renderQuestions();
      document.getElementById('qmsg').textContent=(j.ok?'✓ ':'⚠ ')+(j.msg||'');})
    .catch(e=>{btn.disabled=false;msg.textContent='⚠ '+e;});};
window.qsolve=function(id){
  fetch('/qsolve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})})
    .then(r=>r.json()).then(j=>{QS=j.questions||QS;qbadge();renderQuestions();
      document.getElementById('qmsg').textContent=(j.ok?'✓ ':'⚠ ')+(j.msg||'');});};
const lg=document.getElementById('legend');let lh='<div style="font-weight:600;margin-bottom:5px">Areas</div>';
for(const[a,c]of Object.entries(colors)){if(a==='_other')continue;lh+=`<div class="row"><span class="dot" style="background:${c}"></span>${a}</div>`;}
lh+=`<div style="font-weight:600;margin:8px 0 5px">Nodes</div>
  <div class="row"><span class="dot" style="background:#cdd2e4"></span>today's recommendation (solid)</div>
  <div class="row"><span class="dot" style="background:transparent;border:2px solid #cdd2e4"></span>paper in your library (ring)</div>
  <div class="row"><span class="dot" style="background:#cdd2e4;width:15px;height:15px"></span>interest area (large)</div>`;
lg.innerHTML=lh;
// ---- library search + note reading (Obsidian-in-the-web) ----
const NOTE_TMPL='## 核心思想\n（一两句话：这篇到底做了什么、解决了什么问题）\n\n## 为什么重要 / 我能借鉴\n\n## 和哪些论文相关\n- [[在这里关联其他论文]]\n\n## 疑问 / TODO\n- ';
function isDefaultTmpl(v){const n=(v||'').replace(/\s+/g,' ').trim();return n===''||/Your take: what|\[ \] Worth reading/.test(n);}
window.openNote=function(slug){window._lastView={kind:'note',slug:slug};
  const el0=document.getElementById('detail');el0.dataset.qopen='';el0.dataset.iopen='';
  const el=document.getElementById('detail');el.innerHTML='<div class="empty">loading note…</div>';
  fetch('/note?id='+encodeURIComponent(slug)).then(r=>r.json()).then(j=>{
    if(!j.ok){el.innerHTML='<div class="empty">note not found</div>';return;}
    window._note={slug:slug,below:j.below||''};
    const a=j.arxiv,op=document.getElementById('origpanel'),origOpen=op&&op.style.display==='block';
    let btns='<div class="sec btnrow">';
    if(a){btns+=`<button class="deepbtn" onclick="deepread('${esc(a)}',this)">🔬 ${j.deep?'Regenerate':'Generate'} deep read</button>
      <button class="origbtn" onclick="toggleOrig('${esc(a)}',this)">📄 ${origOpen?'Hide':'Show'} original →</button>
      <button class="origbtn" onclick="toggleQA('${esc(a)}')">💬 提问</button>`;}
    if(j.editable){btns+=`<button class="origbtn" onclick="editNote()">✍️ 写/改综合</button>`;}
    btns+='<span class="deepmsg" id="deepmsg"></span></div>';
    const stars=`<div class="sec"><div class="starrow" id="starrow">${[1,2,3,4,5].map(i=>
      `<span class="star${i<=(j.rating||0)?' on':''}" onclick="rateNote('${esc(slug)}',${i})" title="${i}/5">★</span>`).join('')}
      <span class="deepmsg" id="ratemsg">${j.rating?`${j.rating}/5`:'打分 → 调推荐权重（5=多来这类，1=少来）'}</span></div></div>`;
    let fbrow='';
    if(a){fbrow=`<div class="fb">
      <button class="on" onclick="fb('${esc(a)}','keep',this)">👍 多来这类</button>
      <button class="off" onclick="fb('${esc(a)}','drop',this)">👎 少来这类</button>
    </div><div class="fbmsg" id="fbmsg">${LIVE?'':'(run <code>viz.py --serve</code> for live buttons)'}</div>`;}
    const deepBox=`<div class="deepwrap" id="deepwrap">${j.deep?`<div class="sec"><div class="lab">Deep read (method analysis)</div><div class="md" id="deepmd"></div></div>`:''}</div>`;
    let rel='';
    if(j.related&&j.related.length){
      rel=`<div class="sec"><div class="lab">🔗 相关论文（共享概念）</div>`+
        j.related.map(r=>`<div class="result" data-note="${esc(r.slug)}"><div class="rt">${esc(r.title)}</div>
          <div class="rm">${(r.via||[]).map(esc).join(' · ')}</div></div>`).join('')+`</div>`;
    }
    el.innerHTML=`<div class="card"><h2>${esc(j.title)}</h2>
      <span class="pill">📚 你的库</span>${a?`<span class="pill"><a href="https://arxiv.org/abs/${esc(a)}" target="_blank">arXiv ↗</a></span>`:''}
      ${stars}
      <div class="md note" id="notemd">${md2html(j.md)}</div>
      ${btns}<div id="qabox"></div><div id="noteedit"></div>${deepBox}${rel}${fbrow}</div>`;
    const m=document.getElementById('notemd');
    m.querySelectorAll('.wl').forEach(w=>w.onclick=()=>openNote(w.dataset.note));
    el.querySelectorAll('.result').forEach(x=>x.onclick=()=>openNote(x.dataset.note));
    if(j.deep){const dm=document.getElementById('deepmd');if(dm)dm.innerHTML=md2html(j.deep);}
    typeset(el);
    if(origOpen&&a)loadOrig(a);
  }).catch(e=>{el.innerHTML='<div class="empty">⚠ '+e+'</div>';});
};
// ---- inbox backlog: surfaced but never triaged ----
let IB=DATA.inbox||[];
function ibadge(){const b=document.getElementById('ibadge');if(b)b.textContent=IB.length?`${IB.length} 篇`:'';}
ibadge();
window.showInbox=function(){
  const el=document.getElementById('detail');
  if(el.dataset.iopen==='1'){closeQuestions();return;}     // toggle
  if(LIVE){fetch('/inbox').then(r=>r.json()).then(j=>{IB=j.papers||IB;ibadge();renderInbox();}).catch(()=>renderInbox());}
  else renderInbox();};
window.renderInbox=function(){
  sel=null;dirty=true;const el=document.getElementById('detail');el.dataset.iopen='1';el.dataset.qopen='';
  const rows=IB.map((p,i)=>{
    const badges=(p.venue?` 📌${esc(p.venue)}`:'')+(p.has_code?' 💻':'');
    return `<div class="ibrow" onclick="ibExpand(${i})"><div class="rt">${p.score.toFixed(1)} · ${esc(p.title)}${badges}</div>
      <div class="rm">${esc(p.published)} · ${(p.matched||[]).slice(0,5).map(esc).join(' · ')}</div>
      <div class="ibx" id="ibx${i}" style="display:none" onclick="event.stopPropagation()"></div></div>`;}).join('');
  el.innerHTML=`<div class="card"><h2>📥 未处理的推荐 <button class="qsolve" style="float:right" onclick="closeQuestions()">✕ 返回</button></h2>
    <div class="hinttxt">历史批次里你还没 👍/👎 的论文，按相关性分排序。点开看摘要并处理——处理过的从这里消失，高分论文不再沉底。</div>
    ${rows||'<div class="qnone">全部处理完了 🎉</div>'}</div>`;};
window.ibExpand=function(i){
  const x=document.getElementById('ibx'+i);if(!x)return;
  if(x.style.display==='block'){x.style.display='none';x.innerHTML='';return;}
  // accordion: only one expanded row, so the shared deepwrap/qabox/deepmsg ids stay unique
  document.querySelectorAll('.ibx').forEach(e=>{e.style.display='none';e.innerHTML='';});
  const p=IB[i];x.style.display='block';
  const isArxiv=/^\d{4}\.\d{4,5}$/.test(p.id);
  const tools=isArxiv?`<div class="btnrow" style="margin:6px 0">
      <button class="deepbtn" onclick="deepread('${esc(p.id)}',this)">🔬 ${p.deep?'重新':''}深读</button>
      <button class="origbtn" onclick="toggleOrig('${esc(p.id)}',this)">📄 原文 →</button>
      <button class="origbtn" onclick="toggleQA('${esc(p.id)}')">💬 提问</button>
      <span class="deepmsg" id="deepmsg"></span></div>
    <div id="qabox"></div>
    <div class="deepwrap" id="deepwrap">${p.deep?`<div class="sec"><div class="lab">Deep read</div><div class="md" id="deepmd"></div></div>`:''}</div>`:'';
  x.innerHTML=`<div class="abs" style="margin:8px 0">${esc(p.abstract)}</div>
    ${tools}
    <div class="fb">
      <button class="on" onclick="ibAct(${i},'keep',this)">👍 Keep</button>
      <button class="off" onclick="ibAct(${i},'drop',this)">👎 Drop</button>
      <button class="zo" onclick="ibAct(${i},'add',this)">➕ Zotero+PDF</button>
      <button class="origbtn" onclick="window.open('https://arxiv.org/abs/'+IB[${i}].id)">arXiv ↗</button></div>
    <div class="fbmsg" id="ibmsg${i}">${LIVE?'':'(viz.py --serve 才能操作)'}</div>`;
  if(p.deep){const dm=document.getElementById('deepmd');if(dm)dm.innerHTML=md2html(p.deep);}
  typeset(x);};
window.ibAct=function(i,verdict,btn){
  const p=IB[i],msg=document.getElementById('ibmsg'+i);
  if(!LIVE){msg.innerHTML='需要 <code>viz.py --serve</code>';return;}
  btn.disabled=true;msg.textContent='…';
  const done=()=>{IB.splice(i,1);ibadge();renderInbox();};
  fetch('/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:p.id,verdict})})
    .then(r=>r.json()).then(j=>{
      if(!j.ok){btn.disabled=false;msg.textContent='⚠ '+(j.msg||'失败');return;}
      if(verdict==='add'){   // saving implies keep — also teach the fetcher
        fetch('/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:p.id,verdict:'keep'})}).finally(done);
      }else done();})
    .catch(e=>{btn.disabled=false;msg.textContent='⚠ '+e;});};
// ---- grounded Q&A over the paper's full text ----
window._qa=window._qa||{};
function renderQA(id){
  const box=document.getElementById('qabox');if(!box)return;
  const th=window._qa[id]||[];
  box.innerHTML=`<div class="sec"><div class="lab">💬 问这篇论文 · 基于原文回答，附出处</div>
    <div id="qathread">${th.map(h=>`<div class="qaq">🙋 ${esc(h.q)}</div><div class="qaa md">${md2html(h.a)}</div>`).join('')}</div>
    <textarea id="qain" class="notearea" style="min-height:54px" placeholder="例如：对齐损失加在第几层？为什么是那一层？训练开销增加多少？"></textarea>
    <div class="btnrow" style="margin-top:6px">
      <button class="deepbtn" id="qabtn" onclick="askPaper('${esc(id)}')">提问</button>
      <span class="deepmsg" id="qamsg">${LIVE?'':'(需要 viz.py --serve)'}</span></div></div>`;
  const t=document.getElementById('qathread');if(t)t.scrollTop=t.scrollHeight;
  const ta=document.getElementById('qain');
  ta.addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.metaKey||e.ctrlKey)){e.preventDefault();askPaper(id);}});
  typeset(box);ta.focus();}
window.toggleQA=function(id){
  const box=document.getElementById('qabox');if(!box)return;
  if(box.dataset.open==='1'){box.dataset.open='';box.innerHTML='';return;}
  box.dataset.open='1';renderQA(id);};
window.askPaper=function(id){
  const msg=document.getElementById('qamsg'),btn=document.getElementById('qabtn'),ta=document.getElementById('qain');
  if(!LIVE){msg.innerHTML='需要 <code>viz.py --serve</code>';return;}
  const q=(ta.value||'').trim();if(!q){msg.textContent='先写个问题';return;}
  btn.disabled=true;msg.textContent='📖 读原文并作答…（约 30–60s）';
  const hist=(window._qa[id]||[]).map(h=>({q:h.q,a:h.a}));
  fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,q,history:hist})})
    .then(r=>r.json()).then(j=>{btn.disabled=false;
      if(j.ok){(window._qa[id]=window._qa[id]||[]).push({q:q,a:j.answer});renderQA(id);}
      else msg.textContent='⚠ '+(j.msg||'失败');})
    .catch(e=>{btn.disabled=false;msg.textContent='⚠ '+e;});};
window.rateNote=function(slug,n){
  const msg=document.getElementById('ratemsg');
  if(!LIVE){msg.textContent='需要 viz.py --serve';return;}
  fetch('/rate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:slug,rating:n})})
    .then(r=>r.json()).then(j=>{
      if(j.ok)document.querySelectorAll('#starrow .star').forEach((s,i)=>s.classList.toggle('on',i<n));
      msg.textContent=j.ok?`${n}/5 ✓ 已记录`:'⚠ '+(j.msg||'失败');})
    .catch(e=>{msg.textContent='⚠ '+e;});};
window.editNote=function(){
  const box=document.getElementById('noteedit');
  box.innerHTML=`<div class="sec"><div class="lab">我的笔记 · 写下你的理解（Markdown，可用 [[双链]]）</div>
    <div class="hinttxt">写什么都行，建议回答其中几个：① 核心思想是什么　② 为什么重要 / 我能借鉴什么　③ 和哪些论文相关（用 <code>[[双链]]</code> 关联）　④ 疑问 / 待办。下面已给好骨架，直接填即可。</div>
    <textarea id="notearea" class="notearea"></textarea>
    <div class="btnrow" style="margin-top:8px">
      <button class="deepbtn" onclick="saveNote()">💾 保存</button>
      <button class="origbtn" onclick="document.getElementById('noteedit').innerHTML=''">取消</button>
      <span class="deepmsg" id="savemsg"></span></div></div>`;
  const ta=document.getElementById('notearea');
  let v=(window._note&&window._note.below)||'';
  ta.value=isDefaultTmpl(v)?NOTE_TMPL:v;ta.focus();
};
window.saveNote=function(){
  const slug=window._note&&window._note.slug;if(!slug)return;
  const text=document.getElementById('notearea').value,msg=document.getElementById('savemsg');msg.textContent='保存中…';
  fetch('/savenote',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:slug,text:text})})
    .then(r=>r.json()).then(j=>{if(j.ok){msg.textContent='✓ 已保存';setTimeout(()=>openNote(slug),450);}else{msg.textContent='⚠ '+(j.msg||'失败');}})
    .catch(e=>{msg.textContent='⚠ '+e;});
};
window.editStub=function(arxiv){
  const box=document.getElementById('noteedit');if(!box)return;
  fetch('/stub?id='+encodeURIComponent(arxiv)).then(r=>r.json()).then(j=>{
    window._stub={arxiv:arxiv};
    box.innerHTML=`<div class="sec"><div class="lab">我的速记 · 存到这篇的 Inbox 笔记（Markdown）</div>
      <div class="hinttxt">随手记：这篇值不值得读？核心点是什么？和我在做的有什么关系？</div>
      <textarea id="notearea" class="notearea"></textarea>
      <div class="btnrow" style="margin-top:8px"><button class="deepbtn" onclick="saveStub()">💾 保存</button>
      <button class="origbtn" onclick="document.getElementById('noteedit').innerHTML=''">取消</button>
      <span class="deepmsg" id="savemsg"></span></div></div>`;
    const ta=document.getElementById('notearea');ta.value=isDefaultTmpl(j.below)?'## 速记\n\n':(j.below||'');ta.focus();
  }).catch(e=>{box.innerHTML='<div class="deepmsg">⚠ '+e+'</div>';});
};
window.saveStub=function(){
  const arxiv=window._stub&&window._stub.arxiv;if(!arxiv)return;
  const text=document.getElementById('notearea').value,msg=document.getElementById('savemsg');msg.textContent='保存中…';
  fetch('/savestub',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:arxiv,text:text})})
    .then(r=>r.json()).then(j=>{msg.textContent=j.ok?'✓ 已保存':'⚠ '+(j.msg||'失败');}).catch(e=>{msg.textContent='⚠ '+e;});
};
window.runSearch=function(q){
  const el=document.getElementById('detail');q=(q||'').trim();
  if(q.length<2){el.innerHTML='<div class="empty">Type ≥2 characters to search your library (title · abstract · your highlights).</div>';return;}
  fetch('/search?q='+encodeURIComponent(q)).then(r=>r.json()).then(j=>{
    const rs=j.results||[];
    if(!rs.length){el.innerHTML=`<div class="empty">No library note matches “${esc(q)}”.</div>`;return;}
    el.innerHTML=`<div class="reshead">${rs.length} result${rs.length>1?'s':''} in your library</div>`+
      rs.map(r=>`<div class="result" data-note="${esc(r.slug)}"><div class="rt">${esc(r.title)}</div>
        <div class="rm">${esc(r.coll)}${r.hl?(' · '+r.hl+' 🔖'):''} · …${esc(r.snippet)}…</div></div>`).join('');
    el.querySelectorAll('.result').forEach(x=>x.onclick=()=>openNote(x.dataset.note));
  }).catch(e=>{el.innerHTML='<div class="empty">⚠ '+e+'</div>';});
};
{const ls=document.getElementById('libsearch');let stm;
 if(ls)ls.addEventListener('input',()=>{clearTimeout(stm);stm=setTimeout(()=>runSearch(ls.value),220);});}
loop();
</script></body></html>"""


def library_search(q, limit=40):
    """Full-text search across your library notes (title + abstract + highlights)."""
    q = (q or "").strip().lower()
    if len(q) < 2:
        return []
    out = []
    for f in glob.glob(os.path.join(LIT, "*.md")):
        t = open(f, encoding="utf-8").read()
        low = t.lower()
        if q not in low:
            continue
        m = re.search(r'^title:\s*"?(.*?)"?\s*$', t, re.M)
        title = m.group(1).strip() if m else os.path.basename(f)[:-3]
        cm = re.search(r"^collections:\s*\[(.*)\]", t, re.M)
        coll = (cm.group(1).replace('"', '') if cm else "").strip()
        i = low.find(q)
        snip = re.sub(r"\s+", " ", t[max(0, i - 55):i + 95]).strip()
        out.append({"slug": os.path.basename(f)[:-3], "title": title, "coll": coll,
                    "snippet": snip, "hl": t.count("[!quote]")})
    out.sort(key=lambda x: (0 if q in x["title"].lower() else 1, x["title"].lower()))
    return out[:limit]


def _backlinks(slug):
    """Notes that link to this one (the 'Referenced by' panel, like Obsidian)."""
    needle = "[[" + slug
    out = []
    for d in (LIT, TOPICS):
        for f in glob.glob(os.path.join(d, "*.md")):
            base = os.path.basename(f)[:-3]
            if base == slug:
                continue
            t = open(f, encoding="utf-8").read()
            if needle in t:
                m = re.search(r'^title:\s*"?(.*?)"?\s*$', t, re.M)
                out.append((base, m.group(1).strip() if m else base))
    return out


def related_papers(slug, limit=8):
    """Other library papers that share specific concepts with this one (the graph's
    relatedness, as a clickable list in the note view)."""
    lib = library_index()
    me = next((L for L in lib if L["note"] == slug), None)
    if not me or not me["ek"]:
        return []
    out = []
    for L in lib:
        if L["note"] == slug:
            continue
        shared = me["ek"] & L["ek"]
        if not shared:
            continue
        w = sum(2 if k in STRONG else 1 for k in shared)
        out.append({"slug": L["note"], "title": L["title"], "score": w,
                    "via": sorted(shared)})
    out.sort(key=lambda x: -x["score"])
    return out[:limit]


def note_markdown(slug):
    """Return (title, display_md, below_raw, editable, arxiv) for a note, or (None,…)."""
    if not slug or "/" in slug or "\\" in slug or ".." in slug:
        return None, None, None, None, None
    for d in (LIT, TOPICS):
        p = os.path.join(d, slug + ".md")
        if os.path.exists(p):
            t = open(p, encoding="utf-8").read()
            m = re.search(r'^title:\s*"?(.*?)"?\s*$', t, re.M)
            title = m.group(1).strip() if m else slug
            am = re.search(r"^arxiv:\s*(\S+)\s*$", t, re.M)
            arxiv = am.group(1).strip() if am else ""
            if not arxiv:   # some Zotero items lack the field — recover id from DOI/URL
                m2 = (re.search(r"10\.48550/arXiv\.(\d{4}\.\d{4,5})", t)
                      or re.search(r"arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})", t))
                arxiv = m2.group(1) if m2 else ""
            km = re.search(r"^zotero_key:\s*(\S+)\s*$", t, re.M)
            zkey = km.group(1).strip() if km else ""
            below = t.split(MARKER_NOTE, 1)[1].strip() if MARKER_NOTE in t else ""
            editable = (d == LIT) and (MARKER_NOTE in t)   # only your Literature notes
            body = re.sub(r"^---\n.*?\n---\n", "", t, count=1, flags=re.S)   # drop frontmatter
            body = body.split(MARKER_NOTE, 1)[0]                              # show only the top half
            body = re.sub(r">\s*\[!quote\]\s*(.*)", lambda x: "> 〔" + x.group(1).strip() + "〕", body)
            body = re.sub(r"^\s*#\s+[^\n]*\n", "", body, count=1)             # drop duplicate title heading
            body = re.sub(r"(?im)^\*\*(PDF|Source|Relevance):\*\*.*$", "", body)  # drop file:// / boilerplate
            body = re.sub(r"\n{3,}", "\n\n", body).strip()
            bl = _backlinks(slug)
            if bl:
                body += "\n\n## 🔗 Referenced by\n" + "\n".join(
                    f"- [[{s}|{ti}]]" for s, ti in bl)
            return title, body.strip(), below, editable, arxiv, zkey
    return None, None, None, None, None, None


def save_rating(slug, rating):
    """Store a 1-5 star rating for a library note (keyed by zotero_key in
    Inbox/.ratings.json — sync-proof; paperlib feeds it into the recommender)."""
    try:
        rating = int(rating)
    except (TypeError, ValueError):
        return False, "bad rating"
    if not (1 <= rating <= 5) or not slug or "/" in slug or ".." in slug:
        return False, "bad request"
    p = os.path.join(LIT, slug + ".md")
    if not os.path.exists(p):
        return False, "note not found"
    head = open(p, encoding="utf-8").read(800)
    km = re.search(r"^zotero_key:\s*(\S+)", head, re.M)
    if not km:
        return False, "note has no zotero_key"
    am = re.search(r"^arxiv:\s*(\S+)", head, re.M)
    rp = os.path.join(INBOX, ".ratings.json")
    try:
        data = json.load(open(rp, encoding="utf-8")) if os.path.exists(rp) else {}
    except Exception:
        data = {}
    data[km.group(1)] = {"rating": rating, "slug": slug,
                         "arxiv": am.group(1) if am else "",
                         "date": dt.date.today().isoformat()}
    json.dump(data, open(rp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return True, f"{rating}/5 已记录 — 会影响推荐画像"


def note_rating(zkey):
    rp = os.path.join(INBOX, ".ratings.json")
    try:
        data = json.load(open(rp, encoding="utf-8")) if os.path.exists(rp) else {}
        v = data.get(zkey)
        return int(v["rating"] if isinstance(v, dict) else v) if v else 0
    except Exception:
        return 0


def save_note(slug, text):
    """Write the user's synthesis BELOW the marker; the auto-generated top half is
    never touched (sync-vault preserves it too). Only Literature notes are editable."""
    if not slug or "/" in slug or "\\" in slug or ".." in slug:
        return False, "bad id"
    p = os.path.join(LIT, slug + ".md")
    if not os.path.exists(p):
        return False, "note not found"
    raw = open(p, encoding="utf-8").read()
    if MARKER_NOTE not in raw:
        return False, "note has no editable section"
    head = raw.split(MARKER_NOTE, 1)[0]
    open(p, "w", encoding="utf-8").write(head + MARKER_NOTE + "\n\n" + (text or "").strip() + "\n")
    return True, "saved"


def _find_stub(arxiv):
    """The Inbox stub for a fetched paper (by arXiv id), so you can jot notes on
    today's recommendations before they're in your library."""
    if not re.fullmatch(r"[\w.\-]+", str(arxiv or "")):
        return None
    for f in glob.glob(os.path.join(INBOX, "*.md")):
        t = open(f, encoding="utf-8").read(1200)
        if re.search(rf"^arxiv:\s*{re.escape(str(arxiv))}\s*$", t, re.M):
            return f
    return None


def stub_below(arxiv):
    p = _find_stub(arxiv)
    if not p:
        return None
    t = open(p, encoding="utf-8").read()
    return t.split(MARKER_NOTE, 1)[1].strip() if MARKER_NOTE in t else ""


def save_stub(arxiv, text):
    p = _find_stub(arxiv)
    if not p:
        return False, "no inbox note for this paper"
    raw = open(p, encoding="utf-8").read()
    if MARKER_NOTE not in raw:
        return False, "no editable section"
    head = raw.split(MARKER_NOTE, 1)[0]
    open(p, "w", encoding="utf-8").write(head + MARKER_NOTE + "\n\n" + (text or "").strip() + "\n")
    return True, "saved"


def make_html(date, live=False):
    _, papers = load_last_fetch(date)
    if not papers:
        return None, None
    nodes, edges = build_graph(papers, load_digest(), library_index(), date)
    return render_html(date, nodes, edges, live=live), (nodes, edges)


def _fetch_html(arxiv_id):
    """Raw arXiv HTML render + its base URL (cached). Returns (html, base) or (None,None)."""
    os.makedirs(PDFCACHE, exist_ok=True)
    raw = os.path.join(PDFCACHE, f"{arxiv_id}.raw.html")
    base_f = os.path.join(PDFCACHE, f"{arxiv_id}.base.txt")
    if os.path.exists(raw) and os.path.getsize(raw) > 4000 and os.path.exists(base_f):
        return open(raw, encoding="utf-8").read(), open(base_f, encoding="utf-8").read().strip()
    for v in ("v1", "v2", "v3", ""):
        url = f"https://arxiv.org/html/{arxiv_id}{v}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 paper-agent"})
            with urllib.request.urlopen(req, timeout=30) as r:
                if r.status != 200:
                    continue
                html = r.read().decode("utf-8", "ignore")
        except Exception:
            continue
        if len(html) > 4000:
            open(raw, "w", encoding="utf-8").write(html)
            open(base_f, "w", encoding="utf-8").write(url)   # page URL for urljoin
            return html, url
    return None, None


def _fetch_pdf_bytes(arxiv_id):
    """Download the arXiv PDF (cached). Returns bytes or None. Served locally so the
    original panel can iframe the real PDF without cross-origin framing limits."""
    os.makedirs(PDFCACHE, exist_ok=True)
    p = os.path.join(PDFCACHE, f"{arxiv_id}.pdf")
    if os.path.exists(p) and os.path.getsize(p) > 1000:
        return open(p, "rb").read()
    try:
        req = urllib.request.Request(f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                                     headers={"User-Agent": "Mozilla/5.0 paper-agent"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
        if data[:5] == b"%PDF-":
            open(p, "wb").write(data)
            return data
    except Exception:
        pass
    return None


def _local_pdf(arxiv_id):
    """A PDF for the paper INSIDE the project (so the headless agent may Read it).
    Prefers the user's Zotero copy (often camera-ready), located via the note;
    falls back to downloading the arXiv PDF. Returns a path or None."""
    os.makedirs(PDFCACHE, exist_ok=True)
    p = os.path.join(PDFCACHE, f"{arxiv_id}.pdf")
    if os.path.exists(p) and os.path.getsize(p) > 1000:
        return p
    for f in glob.glob(os.path.join(LIT, "*.md")):
        t = open(f, encoding="utf-8").read(3000)
        if re.search(rf"^arxiv:\s*{re.escape(str(arxiv_id))}\s*$", t, re.M):
            m = re.search(r"file://(\S+?\.pdf)", t)
            if m:
                src = urllib.parse.unquote(m.group(1))
                if os.path.exists(src):
                    shutil.copyfile(src, p)
                    return p
            break
    return p if _fetch_pdf_bytes(arxiv_id) else None


def _pdf_unescape(b):
    def sub(m):
        c = m.group(1)
        if c and all(0x30 <= x <= 0x37 for x in c):   # octal escape \ddd
            return bytes([int(c, 8) & 0xFF])
        return {b"n": b"\n", b"r": b" ", b"t": b" ", b"b": b"", b"f": b""}.get(c, c)
    return re.sub(rb"\\([0-7]{1,3}|.)", sub, b)


def _pdf_extract_text(pdf_path):
    """Crude stdlib text extraction (pdfLaTeX-style PDFs): inflate Flate streams,
    read Tj/TJ show ops. Plenty to ground the LLM; returns '' for PDFs with
    unmappable CID encodings (caller falls back further)."""
    import zlib
    try:
        data = open(pdf_path, "rb").read()
    except OSError:
        return ""
    out = []
    for s in re.findall(rb"stream\r?\n(.*?)endstream", data, re.S):
        try:
            t = zlib.decompress(s)
        except Exception:
            continue
        if b"Tj" not in t and b"TJ" not in t:
            continue
        # linear token scan (a one-regex parse of TJ arrays backtracks
        # catastrophically on multi-MB streams)
        chunk, space = [], False
        for m in re.finditer(
                rb"\((?:[^()\\]|\\.)*\)|-?\d+(?:\.\d+)?|TJ|Tj|T\*|Td|TD", t):
            tok = m.group(0)
            if tok.startswith(b"("):
                if space and chunk:
                    chunk.append(b" ")
                space = False
                chunk.append(_pdf_unescape(tok[1:-1]))
            elif tok in (b"TJ", b"Tj", b"T*", b"Td", b"TD"):
                space = True                   # show-op boundary ≈ word/line break
            else:
                try:                           # big negative kern ≈ word space
                    if float(tok) < -120:
                        space = True
                except ValueError:
                    pass
        if not chunk:
            continue
        # per-stream gate: body text passes; vector-figure glyph soup and
        # CID-encoded streams don't — drop them instead of poisoning the whole
        st = b"".join(chunk).decode("latin-1", "ignore")
        letters = sum(c.isalpha() or c.isspace() for c in st)
        if len(st) > 200 and letters / len(st) > 0.6:
            out.append(st)
    text = "\n".join(out)
    # control chars (octal escapes from odd encodings) break subprocess argv
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text if len(text) > 5000 else ""


def _paper_text(arxiv_id):
    """Full plain text (for deep read / Q&A). arXiv HTML first; local-PDF text
    extraction as fallback (many papers have no HTML render). Cached."""
    cache = os.path.join(PDFCACHE, f"{arxiv_id}.txt")
    if os.path.exists(cache) and os.path.getsize(cache) > 2000:
        return open(cache, encoding="utf-8").read()
    html, _ = _fetch_html(arxiv_id)
    if html:
        html = re.sub(r"(?is)<(script|style|nav|header|footer)\b.*?</\1>", " ", html)
        text = re.sub(r"(?s)<[^>]+>", "\n", html)
        text = re.sub(r"&#?\w+;", " ", text)
        lines, out = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")], []
        for ln in lines:
            if ln == "" and (not out or out[-1] == ""):
                continue
            out.append(ln)
        text = "\n".join(out).strip()
        if len(text) > 2000:
            open(cache, "w", encoding="utf-8").write(text)
            return text
    pdf = _local_pdf(arxiv_id)
    if pdf:
        text = _pdf_extract_text(pdf)
        if text:
            open(cache, "w", encoding="utf-8").write(text)
            return text
    return None


def _paper_html(arxiv_id):
    """Sanitized HTML of the paper for in-panel display (keeps paragraphs, figures,
    tables, MathML). Cached. Returns HTML string or None."""
    cache = os.path.join(PDFCACHE, f"{arxiv_id}.disp.html")
    if os.path.exists(cache) and os.path.getsize(cache) > 1000:
        return open(cache, encoding="utf-8").read()
    html, base = _fetch_html(arxiv_id)
    if not html:
        return None
    m = re.search(r"(?is)<article\b.*?</article>", html)
    body = m.group(0) if m else html
    # drop scripts / chrome
    body = re.sub(r"(?is)<(script|style|nav|header|footer|form|button|select|noscript)\b.*?</\1>", " ", body)
    body = re.sub(r"(?is)\son\w+\s*=\s*(\"[^\"]*\"|'[^']*')", " ", body)  # inline handlers

    def fiximg(mm):
        tag = mm.group(0)
        s = re.search(r"src\s*=\s*[\"']([^\"']+)[\"']", tag)
        if not s:
            return ""
        u = urllib.parse.urljoin(base or "", s.group(1))  # resolve relative to page URL
        a = re.search(r"alt\s*=\s*[\"']([^\"']*)[\"']", tag)
        return f'<img src="{u}" alt="{a.group(1) if a else ""}" loading="lazy">'
    body = re.sub(r"(?is)<img\b[^>]*>", fiximg, body)
    # neutralize links (keep their text)
    body = re.sub(r"(?is)<a\b[^>]*>", "<span>", body).replace("</a>", "</span>")
    # strip ar5iv/ltx UI chrome that clutters reading
    for noise in ("Report issue for preceding element",
                  "Content selection saved. Describe the issue below:",
                  "Generated on", "Report Github Issue"):
        body = body.replace(noise, " ")
    body = re.sub(r"(?is)<(div|span)[^>]*\bclass=\"[^\"]*(ltx_pagination|ltx_page_logo|package-alerts|ltx_listing_data)[^\"]*\"[^>]*>.*?</\1>", " ", body)
    # lone bullet markers (ltx_tag_item) render on their own line — drop them
    body = re.sub(r"(?is)<span[^>]*ltx_tag_item[^>]*>\s*[•·▪]\s*</span>", " ", body)
    # malformed section-number tags ("VI", "-A", "A1") prepended to headings — drop them
    body = re.sub(r"(?is)<span[^>]*ltx_tag_(sub){0,2}section[^>]*>.*?</span>", " ", body)
    body = re.sub(r"(?is)<span[^>]*ltx_tag_appendix[^>]*>.*?</span>", " ", body)
    if len(body) > 1000:
        open(cache, "w", encoding="utf-8").write(body)
        return body
    return None


def answer_question(arxiv_id, q, history=None):
    """Grounded Q&A over the paper's full text. Returns (ok, answer_or_error)."""
    q = (q or "").strip()
    if not q:
        return False, "empty question"
    text = _paper_text(arxiv_id)
    if not text:
        pdf = _local_pdf(arxiv_id)
        if not pdf:
            return False, "no full text available for this paper"
        text = (f"(本篇没有可提取的全文。请先用 Read 工具阅读这个 PDF 再回答："
                f"{pdf})")
    hist = ""
    for h in (history or [])[-4:]:
        if isinstance(h, dict) and h.get("q"):
            hist += f"[此前问答] Q: {str(h['q'])[:200]}\nA: {str(h.get('a',''))[:400]}\n\n"
    prompt = ASK_PROMPT.format(history=hist, text=text[:60000], q=q[:1000])
    return llm.complete(prompt, timeout=300)


def run_deepread(arxiv_id):
    """Fetch the paper's full text (arXiv HTML) and run the 6-section deep-read via
    `claude -p`. Stores the markdown into Inbox/.digest.json under the paper's
    `deep` field. Returns (ok, markdown_or_error)."""
    text = _paper_text(arxiv_id)
    if not text:
        # no arXiv HTML render (common for pre-2024 / failed conversions) —
        # hand the agent the actual PDF to read instead
        pdf = _local_pdf(arxiv_id)
        if not pdf:
            return False, "no arXiv HTML render and no PDF available for this paper"
        text = (f"(本篇没有 arXiv HTML 全文。请先用 Read 工具完整阅读这个 PDF 文件，"
                f"再输出分析：{pdf})")
    prompt = DEEP_PROMPT.format(text=text[:60000])
    ok, deep = llm.complete(prompt)
    if not ok:
        return False, deep
    if len(deep) < 40:
        return False, "agent returned no analysis"
    # persist into the digest so it survives reloads
    p = os.path.join(INBOX, ".digest.json")
    try:
        data = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []
    except Exception:
        data = []
    if isinstance(data, dict):
        data = [{"arxiv": k, **(v if isinstance(v, dict) else {})} for k, v in data.items()]
    hit = next((x for x in data if str(x.get("arxiv") or x.get("id")) == arxiv_id), None)
    if hit is None:
        data.insert(0, {"arxiv": arxiv_id, "deep": deep})
    else:
        hit["deep"] = deep
    json.dump(data, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return True, deep


# ---------------- open questions / ideas panel (questions.md + radar) ------
def questions_payload():
    """Active questions + ideas with their radar hits, for the web panel."""
    import radar
    targets = radar.load_targets()
    hist = radar.load_json(radar.HISTORY, [])
    hits = {}
    for h in hist:
        hits.setdefault(h["target"], []).append({
            "date": h["date"], "title": h["paper_title"], "url": h["url"],
            "relation": h["relation"], "why": h["why"]})
    for t in targets:
        t["hits"] = sorted(hits.get(t["id"], []), key=lambda x: x["date"], reverse=True)
    return targets


def question_add(title, body):
    import radar
    title = " ".join((title or "").strip().lstrip("#").split())
    if not title:
        return False, "标题不能为空"
    if not os.path.exists(radar.QUESTIONS):
        with open(radar.QUESTIONS, "w", encoding="utf-8") as f:
            f.write("# ❓ 开放问题与想法\n")
    text = open(radar.QUESTIONS, encoding="utf-8").read()
    for m in re.finditer(r"^## +(.+?)\s*$", text, re.M):
        if radar.qid(m.group(1).strip()) == radar.qid(title):
            return False, "已有同名问题"
    body = (body or "").strip()
    with open(radar.QUESTIONS, "a", encoding="utf-8") as f:
        f.write("\n## " + title + ("\n\n" + body + "\n" if body else "\n"))
    return True, "已写入 Research/questions.md"


def inbox_backlog():
    """Surfaced-but-untriaged stubs (no 👍/👎 yet), best score first — so a good
    paper from an older batch can't silently drown in Inbox/."""
    handled = set()
    fb = os.path.join(INBOX, ".feedback.jsonl")
    if os.path.exists(fb):
        for line in open(fb, encoding="utf-8"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("arxiv"):
                handled.add(str(r["arxiv"]))
    digest = load_digest()
    out = []
    for f in glob.glob(os.path.join(INBOX, "*.md")):
        t = open(f, encoding="utf-8").read(3000)

        def g(k):
            m = re.search(rf"^{k}:\s*(.*)$", t, re.M)
            return m.group(1).strip() if m else ""
        aid = g("arxiv") or g("s2id")
        if not aid or aid in handled:
            continue
        ab = re.search(r"## Abstract\n(.*?)\n\n", t, re.S)
        out.append({"id": aid, "title": g("title").strip('"'),
                    "score": float(g("score") or 0), "published": g("published"),
                    "has_code": g("has_code") == "true", "venue": g("venue").strip('"'),
                    "matched": [x.strip().strip('"') for x in
                                g("matched").strip("[]").split(",") if x.strip()],
                    "abstract": (ab.group(1).strip() if ab else "")[:900],
                    "deep": (digest.get(aid) or {}).get("deep", "")})
    out.sort(key=lambda x: -x["score"])
    return out


def question_solve(tid):
    import radar
    if not os.path.exists(radar.QUESTIONS):
        return False, "questions.md 不存在"
    lines = open(radar.QUESTIONS, encoding="utf-8").read().splitlines(keepends=True)
    for i, ln in enumerate(lines):
        m = re.match(r"^## +(.+?)\s*$", ln)
        if m and radar.qid(m.group(1).strip()) == tid:
            lines[i] = f"## {m.group(1).strip()} ✅\n"
            with open(radar.QUESTIONS, "w", encoding="utf-8") as f:
                f.writelines(lines)
            return True, "已标记 ✅（雷达将跳过它）"
    return False, "没找到这个问题"


def serve(date, port):
    import http.server
    # An explicit --date is pinned; otherwise every request follows the LATEST
    # fetch — a server left running overnight must not keep serving yesterday.
    pinned = date

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            pth = self.path.split("?")[0]
            if pth == "/pdf":
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                pid = (q.get("id", [""])[0])
                if not re.fullmatch(r"[\w.\-/]+", pid or ""):
                    self.send_response(400); self.end_headers(); return
                data = _fetch_pdf_bytes(pid)
                if not data:
                    self.send_response(404); self.end_headers(); return
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(data); return
            if pth == "/search":
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("q", [""])[0]
                return self._json(200, {"ok": True, "results": library_search(q)})
            if pth == "/note":
                slug = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("id", [""])[0]
                title, md, below, editable, arxiv, zkey = note_markdown(slug)
                if md is None:
                    return self._json(404, {"ok": False, "msg": "note not found"})
                deep = (load_digest().get(str(arxiv), {}) or {}).get("deep", "") if arxiv else ""
                return self._json(200, {"ok": True, "title": title, "md": md, "below": below,
                                        "editable": editable, "arxiv": arxiv,
                                        "rating": note_rating(zkey), "deep": deep,
                                        "related": related_papers(slug)})
            if pth == "/stub":
                aid = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("id", [""])[0]
                below = stub_below(aid)
                return self._json(200, {"ok": below is not None, "below": below or ""})
            if pth == "/questions":
                return self._json(200, {"ok": True, "questions": questions_payload()})
            if pth == "/inbox":
                return self._json(200, {"ok": True, "papers": inbox_backlog()})
            if pth not in ("/", "/index.html"):
                return self._json(404, {"ok": False})
            date = pinned or load_last_fetch(None)[0] or dt.date.today().isoformat()
            page, _ = make_html(date, live=True)
            body = (page or "<h1>no fetched papers</h1>").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store, must-revalidate")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            ln = int(self.headers.get("Content-Length", 0))
            try:
                req = json.loads(self.rfile.read(ln) or b"{}")
            except Exception:
                return self._json(400, {"ok": False, "msg": "bad json"})
            if self.path == "/rate":
                ok, msg = save_rating(str(req.get("id", "")), req.get("rating"))
                return self._json(200, {"ok": ok, "msg": msg})
            if self.path == "/qadd":
                ok, msg = question_add(req.get("title", ""), req.get("body", ""))
                return self._json(200, {"ok": ok, "msg": msg,
                                        "questions": questions_payload()})
            if self.path == "/qsolve":
                ok, msg = question_solve(str(req.get("id", "")))
                return self._json(200, {"ok": ok, "msg": msg,
                                        "questions": questions_payload()})
            if self.path == "/qmatch":
                try:
                    r = subprocess.run([PY, os.path.join(TOOLS, "radar.py")],
                                       capture_output=True, text=True, timeout=600)
                    lines = (r.stdout or r.stderr).strip().splitlines()
                    ok, msg = r.returncode == 0, (lines[-1] if lines else "")
                except Exception as e:
                    ok, msg = False, str(e)[:160]
                return self._json(200, {"ok": ok, "msg": msg[:200],
                                        "questions": questions_payload()})
            pid, verdict = str(req.get("id", "")), req.get("verdict")
            if not re.fullmatch(r"[\w.\-/]+", pid or ""):
                return self._json(400, {"ok": False, "msg": "bad id"})
            if self.path == "/deepread":
                ok, out = run_deepread(pid)
                return self._json(200, {"ok": ok, **({"deep": out} if ok else {"msg": out})})
            if self.path == "/ask":
                ok, out = answer_question(pid, req.get("q"), req.get("history"))
                return self._json(200, {"ok": ok, **({"answer": out} if ok else {"msg": out})})
            if self.path == "/savenote":
                ok, msg = save_note(pid, req.get("text", ""))
                return self._json(200, {"ok": ok, "msg": msg})
            if self.path == "/savestub":
                ok, msg = save_stub(pid, req.get("text", ""))
                return self._json(200, {"ok": ok, "msg": msg})
            if self.path == "/fulltext":
                doc = _paper_html(pid)
                if doc:
                    return self._json(200, {"ok": True, "html": doc})
                return self._json(200, {"ok": False, "msg": "no arXiv HTML full text for this paper"})
            if self.path != "/feedback" or verdict not in ("keep", "drop", "add"):
                return self._json(400, {"ok": False, "msg": "bad request"})
            if verdict == "add":
                cmd = [PY, os.path.join(TOOLS, "zotero_add.py"), pid]
                ok_msg = "saved to Zotero with PDF (selected collection)"
            else:
                cmd = [PY, os.path.join(TOOLS, "feedback.py"), verdict, pid]
                ok_msg = "recorded: more like this ↑" if verdict == "keep" else "recorded: less like this ↓"
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            except Exception as e:
                return self._json(200, {"ok": False, "msg": str(e)[:120]})
            ok = r.returncode == 0
            msg = ok_msg if ok else (r.stderr or r.stdout or "failed").strip()[:160]
            return self._json(200, {"ok": ok, "msg": msg})

    # Threaded: a keep-alive browser connection must not block feedback POSTs.
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    url = f"http://127.0.0.1:{port}/"
    print(f"serving live graph ({pinned or 'latest fetch'}) at {url}  (Ctrl-C to stop)")
    webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date")
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()

    if args.serve:
        return serve(args.date, args.port)

    date, papers = load_last_fetch(args.date)
    if not papers:
        print("no fetched papers found (run tools/fetch.py first)")
        return
    page, (nodes, edges) = make_html(date)
    os.makedirs(DAILY, exist_ok=True)
    out = os.path.join(DAILY, f"{date}-graph.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    n = lambda ty: sum(1 for x in nodes if x["type"] == ty)
    lib_e = sum(1 for e in edges if e["kind"] == "lib")
    print(f"wrote {os.path.relpath(out, ROOT)}  ({n('paper')} papers, {n('area')} areas, "
          f"{n('lib')} related library papers, {lib_e} paper↔library links)")
    print("tip: run `python3 tools/viz.py --serve` for clickable 👍/👎/➕ feedback.")
    if args.open:
        webbrowser.open("file://" + out)


if __name__ == "__main__":
    main()
