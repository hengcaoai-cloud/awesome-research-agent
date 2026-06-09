---
description: Library Q&A — answer a question, digest a paper, or surface connections
---

Unified library question-answering. Input: $ARGUMENTS

**Route by what the input is:**

- Looks like **one specific paper** — an arXiv id (`2606.07100`), a `[[note]]`, a
  Zotero key, or `paper: <title>` → **Digest a paper** below.
- Starts with **`connect`** / **`links`** (optionally a theme after it), or is empty
  → **Find connections** below.
- Otherwise (a **question**) → **Answer a question** below. This is the default.

---

### Answer a question  (the main job)
1. Find relevant notes: `rg -l -i "<key terms>" Literature/ Topics/` and
   `python3 tools/zotero_read.py search "<term>"`. Broaden terms if results are thin.
2. Read the strongest 3–8 notes — **highlights and the user's synthesis first**.
   Open a PDF (path in note frontmatter) only when metadata is insufficient.
3. Synthesize across papers: the consensus, the disagreements, the lineage, the
   open gaps. Ground every claim in a `[[note]]`; quote the user's own highlights
   where they bear on the question.
4. If the library genuinely lacks coverage, say so plainly and offer to fetch
   (`/papers fetch`) or search the web — don't substitute generic knowledge.
5. Close with: **Most relevant notes** (3–5 `[[links]]`) and **Suggested next reads**.

### Digest a paper
1. Resolve it: `python3 tools/zotero_read.py search "<title words>"` or use the given
   key/note. If in Zotero, refresh its note first: `python3 tools/lit_note.py sync
   <KEY>`. If it's only an arXiv id not yet in the library, fetch the abstract and
   offer to add it (`python3 tools/zotero_add.py <arxiv_id>`).
2. **Deep read (default for a single paper).** Read the PDF (path in the note's
   frontmatter; pull it if metadata is thin) and produce the full analysis in the
   user's preferred 6-section structure — see `Research/paper-reading-template.md`
   and follow it exactly: 0 摘要翻译 · 1 方法动机 · 2 方法设计(最细致, 主要目标) ·
   3 与其他方法对比(含创新点三段式 + 对比表) · 4 实验表现与优势 · 5 学习与应用 ·
   6 总结(一句话核心 + 第一性原理问句 + 速记 pipeline). Chinese, rigorous, **method-
   focused**. Weave in the user's own highlights (`## My Highlights`) where they bear
   on a section. (For a quick skim instead, the user can say "简要" — then give just
   Problem / Method / Key results / Neighbours / Open questions.)
3. **Lineage (when useful):** run `python3 tools/s2_graph.py <arxiv_id>` for the
   influential **references** (what it builds on) and recent **citing** papers (the
   frontier). Flag frontier papers not yet in the library as fetch candidates,
   prioritizing 📌top-venue + 💻code; note which are already `[[notes]]`.
4. Offer to draft a paragraph into the note's **Synthesis** section — only **below**
   the marker line, and only after the user agrees.

### Find connections
1. Scan `Literature/` and `Topics/` (grep titles, highlights, synthesis). If a theme
   was given, focus there; else range library-wide.
2. Find 5–8 **non-obvious** pairs/clusters: papers sharing a mechanism, tackling the
   same bottleneck from different angles, contradicting each other, or where one
   supplies what another lacks — especially across *different* Topics (e.g. a CV
   spatial-reasoning idea applicable to a VLA paper).
3. Explain each connection in 1–2 lines, grounded in the user's highlights where
   possible, naming the two `[[notes]]`.
4. Offer to add `[[wikilinks]]` into each note's **Connections** section (below the
   marker line only) so the Obsidian graph reflects them — ask before editing.
