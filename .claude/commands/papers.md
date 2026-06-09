---
description: Daily paper flow — fetch, digest (reading plan + graph), triage, keep/drop
---

The paper-flow hub. First token of the argument is the action; the rest are its
args. Action = $ARGUMENTS

Dispatch on the first word:

- **(empty) or `fetch`** → run **Fetch** below, then **Digest**.
- **`digest`** → **Digest** only (papers already in `Inbox/`; do NOT fetch again).
- **`triage`** → **Triage** below.
- **`keep <id…>`** → **Keep** below.
- **`drop <id…>`** → **Drop** below.

Pass any extra flags through (e.g. `fetch --source s2 --top 20`).

---

### Fetch
1. Run `python3 tools/fetch.py <flags>`. It learns the interest profile from the
   Zotero library (highlighted papers weighted higher) + `.interests.yaml`, recalls
   from **arXiv** (today's newest) and **Semantic Scholar recommendations** (seeded
   by your library), dedupes vs Zotero and already-surfaced papers, and writes
   ranked stubs to `Inbox/`.
2. Report two buckets: **Fresh (arXiv)** = today's newest; **Recommended (S2)** =
   interest-adaptive discovery. One-line "why relevant" each; link related `[[Topic]]`.
3. Append a dated summary to `Daily/<today>.md`.
4. **Auto-fill value cards + graph:** run `python3 tools/digest_cards.py` (one batched
   `claude -p` call → problem/innovation/directions for every new paper into
   `Inbox/.digest.json`) then `python3 tools/viz.py`. (The daily 07:00 job does this
   automatically; do it here too on demand.)
5. Do not auto-add to Zotero; only on request (needs the local connector enabled —
   `python3 tools/zotero_add.py <arxiv_id>`).

### Digest (reading plan + knowledge graph)
Papers were just fetched into `Inbox/` (do NOT fetch again). Produce a prioritized
reading plan **and** the interactive value graph.
1. List today's new stubs: `ls -t Inbox/*.md | head -20`; read the ones whose
   filename starts with today's date (frontmatter: title, source, score, matched,
   venue, has_code; plus abstract).
2. Group by the user's areas: **embodied foundation models (WAM/VLA)**, **tactile /
   contact-rich manipulation**, **multimodal / vision foundation models / spatial
   intelligence**, **representation learning for action**, **embodied LLM**. Skip
   off-topic ones.
3. For the 3–5 most relevant, write one line each: what's new + why it connects to
   the user's library (name the related `[[Topic]]` or `[[note]]`). Append under a
   `## Reading plan` heading in `Daily/<today>.md`. Keep it tight.
4. Value cards for **every** new paper (*problem* / *innovation* / *directions*) are
   generated automatically: run `python3 tools/digest_cards.py` (batched `claude -p`
   → `Inbox/.digest.json`, idempotent). `--all` to regenerate existing ones.
5. Render the graph: `python3 tools/viz.py` writes `Daily/<today>-graph.html`
   (static). Edges link each paper to its interest **areas** and to the specific
   **library papers it shares concepts with**. For clickable in-graph feedback,
   start `python3 tools/viz.py --serve` and give the user the URL — the detail
   panel's 👍 (feedback keep) / 👎 (feedback drop) / ➕ (zotero_add + PDF) buttons
   teach the fetcher and save papers without leaving the graph.
6. Note which (if any) look strong enough to add to Zotero, but do not add them.

### Triage
Fast, clickable triage of freshly fetched papers (optional date as extra arg).
1. Find the stubs: today's `Inbox/*.md` (or the given date), newest first. Read each
   one's frontmatter (title, score, venue, has_code, source) and abstract.
2. Per paper, a tight 2–3 line summary: core idea + why it relates to the user's
   work (name a `[[Topic]]`/`[[note]]`); call out **📌 top-venue** and **💻 has-code**
   (the user prioritizes reproducible top-venue work).
3. Collect feedback with the **AskUserQuestion tool** so the user just clicks. Use
   `multiSelect: true`, batches of ≤4 papers per question (paginate if more): one
   "👍 Which to keep?", one "👎 Any to suppress?". Short paper-title labels.
4. Apply: liked → `python3 tools/feedback.py keep <id>`; disliked →
   `python3 tools/feedback.py drop <id>`; unselected → neutral. If a liked paper is
   📌top-venue or the user says "save it", offer
   `python3 tools/zotero_add.py <arxiv_id>` (needs the local connector).
5. Confirm what was learned in one line; note any profile shift.

### Keep
Arg = arXiv id / S2 id / title (resolve via grep `Inbox/`).
1. `python3 tools/feedback.py keep <id>` (kept ids become future S2 seeds).
2. To also save to Zotero: `python3 tools/zotero_add.py <arxiv_id>` — downloads the
   **actual PDF** as a stored attachment and **auto-routes to the `Recommend`
   collection** (no UI click needed; `--collection NAME` to override). Needs the
   local connector on.
3. If the user signals a broader interest shift ("more like this"), nudge
   `.interests.yaml` boost terms — see CLAUDE.md "Evolving".

### Drop
Arg = arXiv id / S2 id / title.
1. `python3 tools/feedback.py drop <id>` — records a negative signal, removes the
   Inbox stub. Dropped ids suppress similar recommendations.
2. If the user dislikes a whole theme ("stop showing me X"), add X to the `mute`
   list in `.interests.yaml` — see CLAUDE.md "Evolving".
