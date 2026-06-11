---
description: Synthesis & ideation — gaps, ideas, or the weekly digest
---

Research synthesis hub. First token = mode; the rest = its args. Input: $ARGUMENTS

Dispatch on the first word:
- **`gaps [area]`** → **Gaps** below.
- **`ideas [seed]`** → **Ideas** below.
- **`weekly`** → **Weekly** below.
- **`questions [add <text>]`** → **Questions** below (开放问题 + 雷达).
- **`glossary`** → **Glossary** below (概念词汇表).

If no mode is given, ask which the user wants (gaps / ideas / weekly / questions).

**North star (orient everything to this):** truly realizing embodied intelligence —
robots that, like people, enter society and create real-world value. Favor
generality, open-world robustness, physical common sense, and learning efficiency
over incremental benchmark gains.

---

### Gaps
1. Read widely across `Literature/` (prioritize papers with many highlights) and the
   `Topics/` MOCs. Pay special attention to **limitations / future-work** language in
   abstracts and to what the user *highlighted* — repeated pain points are signal.
2. Identify 4–6 concrete **gaps**: bottlenecks multiple papers acknowledge but none
   solve, capability cliffs, evaluation holes, or shared assumptions that may be
   wrong. Ground each in 2–3 specific `[[notes]]`/highlights.
3. For each gap: *why it blocks progress toward the north star* and how hard it looks.
4. Rank by (impact toward the north star × tractability for a solo/small team).
5. For the top gaps, point to the closest existing methods that could be recombined.
   Offer to spin a promising one into `/research ideas` for full ideation + novelty
   check. Save to `Research/gaps-<date>.md`.

### Ideas
1. Ground in the user's library: what are they already deep in (highlighted papers,
   Topics)? Build *from* their strengths (WAM/VLA, tactile, spatial intelligence,
   representation-for-action, embodied LLM) so ideas are actionable, then push beyond.
2. Propose 4–6 directions. For each:
   - **The idea** in 2–3 sentences (the core mechanism / hypothesis).
   - **Why now** — what recent capability makes it newly feasible.
   - **Why it matters** for the north star.
   - **First experiment** — a concrete, small, reproducible v0 (datasets/sim,
     baseline, metric) a small team could run.
   - **Closest prior work** in their library (`[[notes]]`) and the white space.
3. Stretch ≥1 idea well beyond the current frontier (a contrarian / cross-disciplinary
   bet), clearly labeled high-risk.
4. Use the **idea-generation** and **novelty-assessment** skills to refine and
   sanity-check novelty against the literature; drop or sharpen anything already done.
5. Save to `Research/ideas/<date>-<slug>.md` with a one-line index entry, and ask
   which to develop into a full plan (research-planning / experiment-design skills).

### Weekly
1. Gather the week: stubs in `Inbox/` from the last 7 days, notes whose `zotero_added`
   is within the week, and the week's `Daily/*.md` logs.
2. Per the user's areas (embodied FM / WAM / VLA, tactile, multimodal+vision FM +
   spatial intelligence, representation-for-action, embodied LLM), write a tight
   **"what moved this week"**: 3–5 themes, each 2–3 sentences, citing specific papers
   (`[[notes]]` / arXiv ids). Highlight 📌top-venue + 💻reproducible work to read.
3. **Trajectory** — one short paragraph: where each active thread seems headed and
   what the field is converging on or struggling with.
4. **Directions to consider** — 2–3 short provocations toward the north star that this
   week's work suggests; offer `/research ideas` to develop any into a full proposal.
5. **积压重浮**: include the output of `python3 tools/backlog.py` (papers saved
   >2 weeks ago with zero highlights/notes) — gently suggest reading or releasing.
6. **雷达周报**: if `Research/radar.md` gained hits this week, roll them up in 2-3
   lines (which questions/ideas got new evidence or collision risks).
7. Save to `Research/weekly/<YYYY-Www>.md` and add a one-line pointer. Keep it to
   ~one screen — orientation, not a survey.

### Questions（开放问题 + 雷达）
The user's open problems live in `Research/questions.md` (one `## ` section each);
daily fetch matches new papers against them via `tools/radar.py` → hits accumulate
in `Research/radar.md`.
1. No args → review: read `questions.md` + `radar.md`, summarize per question the
   recent hits (relation + why), and suggest: which question has enough new
   material to act on (offer `/research ideas` seeded by it), which looks solved
   by the field (suggest marking ✅), which needs sharper wording for better
   matching.
2. `add <text>` → append a well-formed `## ` section to `questions.md`: title =
   the question, body = 2-4 sentences of context written WITH the user (what's
   blocking, their hunch). Then run `python3 tools/radar.py` so today's batch is
   matched immediately.
3. When the user mentions an unsolved problem in conversation, offer to record
   it here.

### Glossary（概念词汇表）
1. `python3 tools/glossary.py` rebuilds `Topics/Concepts.md`: every specific
   concept → the papers discussing it (**bold** = appears in the user's
   highlights), with cached 1-2 句中文定义 (only new concepts cost a call).
2. Report what changed: new concepts since last build, concepts whose paper
   count grew. Point out concepts with many *mentioned* but zero *engaged*
   papers — areas the user collects but hasn't really read.
