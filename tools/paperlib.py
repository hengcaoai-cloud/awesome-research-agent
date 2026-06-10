#!/usr/bin/env python3
"""Shared library for the paper fetcher: config, interest profile, scoring,
dedup, stub writing, and the two recall sources (arXiv + Semantic Scholar).

Stdlib only. Reads Zotero read-only via zotero_read.py.
"""
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "Inbox")
READER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zotero_read.py")
CONF = os.path.join(ROOT, ".interests.yaml")
FEEDBACK = os.path.join(ROOT, "Inbox", ".feedback.jsonl")
SURFACED = os.path.join(ROOT, "Inbox", ".surfaced.txt")
MARKER = "<!-- ===== Below this line is yours; sync never touches it ===== -->"

STOP = set("""a an the of for and or to in on with from this that these those we our
is are be as by at it its their using use used via toward towards can may also new
approach method model models task tasks results show propose present paper study
based learning network networks deep neural large between which while where when
than then more most much such not no into over under each both per we propose""".split())


def reader(*args):
    out = subprocess.check_output([sys.executable, READER, *args], text=True)
    return json.loads(out) if out.strip() else None


# ---------------------------------------------------------------- config
def load_conf():
    conf = {"arxiv_categories": ["cs.RO", "cs.CV", "cs.LG", "cs.AI"],
            "boost": {}, "mute": [], "max_candidates": 240, "top_n": 14,
            "min_score": 1.0, "lookback_days": 3, "s2_enabled": 1,
            "s2_seeds": 40, "s2_limit": 30, "s2_bonus": 4.0}
    if not os.path.exists(CONF):
        return conf
    cur = None
    for raw in open(CONF, encoding="utf-8"):
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" ") and line.endswith(":"):
            cur = line[:-1].strip()
            if cur == "boost":
                conf[cur] = {}
            elif cur in ("arxiv_categories", "mute"):
                conf[cur] = []
            continue
        if line.startswith(" ") and line.strip().startswith("- "):
            conf.setdefault(cur, []).append(line.strip()[2:].strip())
        elif line.startswith(" ") and ":" in line:
            k, v = line.strip().split(":", 1)
            conf[cur][k.strip()] = float(v.strip())
        elif ":" in line:
            k, v = line.split(":", 1)
            v = v.strip()
            if v:
                conf[k.strip()] = float(v) if re.fullmatch(r"[\d.]+", v) else v
    for k in ("max_candidates", "top_n", "lookback_days", "s2_enabled", "s2_seeds", "s2_limit"):
        conf[k] = int(float(conf[k]))
    for k in ("min_score", "s2_bonus"):
        conf[k] = float(conf[k])
    return conf


# ---------------------------------------------------------------- profile
def tokenize(text):
    for w in re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", (text or "").lower()):
        w = w.strip("-")
        if w and w not in STOP and len(w) > 2:
            yield w


def library_index():
    """Return (items, existing_arxiv_ids, existing_titles_normalized)."""
    items = reader("list")
    arxiv, titles = set(), set()
    for it in items:
        if it.get("arxiv"):
            arxiv.add(it["arxiv"])
        titles.add(norm_title(it["title"]))
    return items, arxiv, titles


def norm_title(t):
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())[:60]


def learn_profile(items, conf):
    freq = {}
    for it in items:
        # weight highlighted papers higher: they signal real engagement
        w_mult = 1 + min(it.get("nAnnotations", 0), 10) / 5.0
        text = it["title"] + " " + " ".join(it.get("tags", []))
        for w in tokenize(text):
            freq[w] = freq.get(w, 0) + w_mult
    weights = {}
    if freq:
        mx = max(freq.values())
        weights = {w: 0.5 + c / mx for w, c in freq.items() if c >= 2}
    return weights


def load_feedback():
    """Return (positive_ids, negative_ids) from triage feedback."""
    pos, neg = set(), set()
    if os.path.exists(FEEDBACK):
        for line in open(FEEDBACK, encoding="utf-8"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            aid = r.get("arxiv")
            if not aid:
                continue
            (pos if r.get("verdict") == "keep" else neg).add(aid)
    return pos, neg


def load_surfaced():
    if not os.path.exists(SURFACED):
        return set()
    return set(l.strip() for l in open(SURFACED, encoding="utf-8") if l.strip())


def mark_surfaced(ids):
    os.makedirs(INBOX, exist_ok=True)
    with open(SURFACED, "a", encoding="utf-8") as f:
        for i in ids:
            if i:
                f.write(i + "\n")


CODE_RE = re.compile(
    r"github\.com/|gitlab\.com/|\bcode (?:is |will be )?(?:available|released)|"
    r"\bwe release\b|project page|\bopen-?sourced?\b|huggingface\.co/", re.I)


def venue_match(text, conf):
    """Return the matched top-venue name, or None."""
    low = text.lower()
    for v in conf.get("top_venues", []):
        # word-ish match to avoid 'icra' inside another word
        if re.search(rf"\b{re.escape(v.lower())}\b", low):
            return v
    return None


def score(cand, weights, conf):
    text = (cand["title"] + " " + cand.get("abstract", "")).lower()
    s = sum(weights[w] for w in set(tokenize(text)) if w in weights)
    hits = []
    for phrase, mult in conf.get("boost", {}).items():
        if phrase.lower() in text:
            s += mult
            hits.append(phrase)
    if cand.get("source") == "s2":
        s += conf["s2_bonus"]          # came from interest-adaptive recommender
    # reproducibility: code released / project page
    if CODE_RE.search(cand.get("abstract", "") + " " + cand.get("venue_hint", "")):
        s += conf.get("code_boost", 3.0)
        hits.append("code")
        cand["has_code"] = True
    # top venue (from arxiv comment/journal_ref or S2 venue field)
    vtext = " ".join([cand.get("venue_hint", ""), cand.get("venue", "")])
    v = venue_match(vtext, conf)
    if v:
        s += conf.get("venue_boost", 5.0)
        hits.append(f"@{v}")
        cand["venue_matched"] = v
    cand["_hits"] = hits
    cand["_score"] = round(s, 1)
    return s


def muted(cand, conf):
    text = (cand["title"] + " " + cand.get("abstract", "")).lower()
    return any(m.lower() in text for m in conf.get("mute", []))


# ---------------------------------------------------------------- recall: arXiv
def arxiv_recall(conf, lookback_cutoff):
    """Scan each category by paginating newest→oldest until we pass the lookback
    cutoff. This covers the FULL window even for high-volume categories like cs.CV
    (a fixed 'newest N' budget only reaches a few hours back there, silently missing
    relevant older-but-in-window papers)."""
    out = []
    ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    page = 200
    cap = max(int(conf.get("max_candidates", 240)), 800)   # safety cap scanned per category
    for cat in conf["arxiv_categories"]:
        start, stop = 0, False
        while start < cap and not stop:
            url = ("http://export.arxiv.org/api/query?" + urllib.parse.urlencode({
                "search_query": f"cat:{cat}", "sortBy": "submittedDate",
                "sortOrder": "descending", "start": start, "max_results": min(page, cap - start)}))
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "paper-agent/1.0"})
                with urllib.request.urlopen(req, timeout=45) as r:
                    root = ET.fromstring(r.read())
            except Exception as e:
                print(f"warn: arxiv {cat} @{start}: {e}", file=sys.stderr)
                break
            entries = root.findall("a:entry", ns)
            if not entries:
                break
            for e in entries:
                aid = e.find("a:id", ns).text
                m = re.search(r"(\d{4}\.\d{4,5})", aid)
                pub = e.find("a:published", ns).text[:10]
                if pub < lookback_cutoff:
                    stop = True                # descending → the rest are older too
                    continue
                comment_el = e.find("arxiv:comment", ns)
                journal_el = e.find("arxiv:journal_ref", ns)
                out.append({
                    "arxiv": m.group(1) if m else aid,
                    "title": " ".join(e.find("a:title", ns).text.split()),
                    "abstract": " ".join(e.find("a:summary", ns).text.split()),
                    "authors": [a.find("a:name", ns).text for a in e.findall("a:author", ns)],
                    "published": pub, "url": aid,
                    "categories": [c.get("term") for c in e.findall("a:category", ns)],
                    "venue_hint": " ".join(x.text for x in (comment_el, journal_el) if x is not None),
                    "source": "arxiv"})
            start += page
            if not stop and start < cap:
                time.sleep(3)                  # arxiv asks for ~3s between requests
    return out


# ---------------------------------------------------------------- recall: Semantic Scholar
def s2_request(method, url, body=None, tries=3):
    key = os.environ.get("S2_API_KEY")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["x-api-key"] = key
    data = json.dumps(body).encode() if body is not None else None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, method=method, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < tries - 1:
                time.sleep(3 * (i + 1))
                continue
            print(f"warn: s2 {e.code}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"warn: s2 {e}", file=sys.stderr)
            return None
    return None


def s2_recall(items, conf, neg_ids, pos_ids=None):
    """Interest-adaptive recommendations seeded by the user's own library."""
    if not conf.get("s2_enabled"):
        return []
    # seeds: most-annotated + most-recent library papers that have arXiv ids,
    # plus papers the user explicitly 'kept' during triage.
    seeds = [it for it in items if it.get("arxiv")]
    seeds.sort(key=lambda x: (x.get("nAnnotations", 0), x.get("dateAdded", "")), reverse=True)
    pos = [f"ARXIV:{a}" for a in (pos_ids or []) if re.fullmatch(r"\d{4}\.\d{4,5}", a)]
    pos += [f"ARXIV:{it['arxiv']}" for it in seeds[:conf["s2_seeds"]]]
    pos = list(dict.fromkeys(pos))  # dedupe, keep order
    if not pos:
        return []
    neg = [f"ARXIV:{a}" for a in list(neg_ids)[:40]]
    url = ("https://api.semanticscholar.org/recommendations/v1/papers?"
           + urllib.parse.urlencode({
               "fields": "title,abstract,year,externalIds,publicationDate,authors,"
                         "venue,openAccessPdf",
               "limit": conf["s2_limit"]}))
    res = s2_request("POST", url, {"positivePaperIds": pos, "negativePaperIds": neg})
    if not res:
        return []
    out = []
    for p in res.get("recommendedPapers", []):
        ext = p.get("externalIds") or {}
        aid = ext.get("ArXiv")
        pub = p.get("publicationDate") or (str(p["year"]) + "-01-01" if p.get("year") else "")
        out.append({
            "arxiv": aid, "s2id": p.get("paperId"),
            "title": p.get("title") or "", "abstract": p.get("abstract") or "",
            "authors": [a.get("name") for a in (p.get("authors") or [])],
            "published": (pub or "")[:10],
            "url": (f"https://arxiv.org/abs/{aid}" if aid
                    else f"https://www.semanticscholar.org/paper/{p.get('paperId')}"),
            "venue": p.get("venue") or "",
            "categories": [], "source": "s2"})
    return out


# ---------------------------------------------------------------- dedup + stubs
def dedup(cands, existing_arxiv, existing_titles):
    seen, out = set(), []
    for c in cands:
        key = c.get("arxiv") or c.get("s2id") or norm_title(c["title"])
        if key in seen:
            continue
        if c.get("arxiv") and c["arxiv"] in existing_arxiv:
            continue
        if norm_title(c["title"]) in existing_titles:
            continue
        seen.add(key)
        out.append(c)
    return out


def write_stub(c):
    os.makedirs(INBOX, exist_ok=True)
    slug = re.sub(r"[^\w]+", "-", c["title"].lower())[:60].strip("-") or "untitled"
    date = c.get("published") or dt.date.today().isoformat()
    path = os.path.join(INBOX, f"{date}-{slug}.md")
    if os.path.exists(path):
        return path
    ident = (f"[arXiv:{c['arxiv']}](https://arxiv.org/abs/{c['arxiv']})" if c.get("arxiv")
             else f"[S2]({c['url']})")
    fm_arxiv = c.get("arxiv") or ""
    badges = []
    if c.get("venue_matched"):
        badges.append(f"📌 {c['venue_matched']}")
    if c.get("has_code"):
        badges.append("💻 code")
    badge_str = ("  ·  " + "  ·  ".join(badges)) if badges else ""
    body = f"""---
title: {json.dumps(c['title'], ensure_ascii=False)}
arxiv: {fm_arxiv}
s2id: {c.get('s2id','')}
authors: [{', '.join(json.dumps(a, ensure_ascii=False) for a in (c.get('authors') or [])[:10])}]
published: {date}
source: {c.get('source','')}
venue: {json.dumps(c.get('venue_matched') or c.get('venue') or '', ensure_ascii=False)}
has_code: {str(bool(c.get('has_code'))).lower()}
score: {c.get('_score',0)}
matched: [{', '.join(json.dumps(h) for h in c.get('_hits',[]))}]
status: inbox
---

# {c['title']}{badge_str}

**Authors:** {', '.join((c.get('authors') or [])[:6])}
**Source:** {c.get('source','')} · {ident} · {date}
**Relevance:** {c.get('_score',0)}  (matched: {', '.join(c.get('_hits',[])) or '—'})

## Abstract
{c.get('abstract') or '(no abstract)'}

{MARKER}

## Triage
- [ ] Worth reading?
- [ ] Save to Zotero  (`/papers keep {fm_arxiv or c.get('s2id','')}` teaches the agent)
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return path
