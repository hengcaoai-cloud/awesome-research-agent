---
description: Synthesis & ideation — gaps, ideas, or the weekly digest
---

Research synthesis hub. First token = mode; the rest = its args. Input: $ARGUMENTS

Dispatch on the first word:
- **`gaps [area]`** → **Gaps** below.
- **`ideas [seed]`** → **Ideas** below.
- **`weekly`** → **Weekly** below.

If no mode is given, ask which the user wants (gaps / ideas / weekly).

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
5. Save to `Research/weekly/<YYYY-Www>.md` and add a one-line pointer. Keep it to
   ~one screen — orientation, not a survey.
