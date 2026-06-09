<!-- AGENTS.md — agent instructions for OpenAI Codex.
     This project is agent-agnostic. AGENTS.md mirrors CLAUDE.md (the canonical
     instructions for Claude Code). If you edit one, mirror the change, e.g.:
        { printf '<!-- ... header ... -->\n\n'; cat CLAUDE.md; } > AGENTS.md
     Select the agent the Python tools call with:  RESEARCH_AGENT_LLM=claude|codex -->

# Research Agent — Zotero × Obsidian

This is both a Claude Code project and an Obsidian vault. It turns a Zotero
library + Obsidian notes into a research assistant that fetches papers, reads
them, and answers questions grounded in the user's own library and highlights.

## North star

The user's research goal is **truly realizing embodied intelligence — robots
that, like people, enter society and create real-world value.** Orient ideation,
gap-finding, and prioritization to this: favor generality, open-world robustness,
physical common sense, and learning efficiency over incremental benchmark gains.
The user also prefers **top-venue, reproducible (has-code) work** — surface and
weight those (the fetcher already boosts 📌venue and 💻code).

## Layout

- `Literature/` — one note per paper. The **top half** (above the marker line
  `<!-- ===== Below this line is yours ... -->`) is auto-generated from Zotero
  (metadata, abstract, the user's highlights, the user's Zotero notes). The
  **bottom half** is the user's own synthesis — **never overwrite it**.
- `Topics/` — one MOC per Zotero collection (World Model, VLA, CV, Robotics,
  MLLM, ML, Foundation Model, Diffusion). These are the knowledge-graph hubs.
- `Inbox/` — newly fetched candidates awaiting triage. `.feedback.jsonl` (keep/drop
  signals) and `.surfaced.txt` (already-shown ids) live here.
- `Daily/` — fetch logs + reading plans, dated `YYYY-MM-DD.md`.
- `Research/` — `gaps-<date>.md`, `ideas/`, and `weekly/` synthesis outputs.
- `tools/` — Python scripts (stdlib only). `.interests.yaml` tunes the fetcher.

## Data sources & trust order

When answering, prefer evidence in this order:
1. **The user's highlights** (`## My Highlights`) and **Zotero notes** — these
   are what *they* flagged as important. Cite them.
2. The user's synthesis sections (bottom half of notes, Topic MOCs).
3. Paper abstracts in the notes.
4. Full PDF text (read from the `PDF:` path in a note's frontmatter only when
   the note's metadata is insufficient).
5. The web / arXiv (only when the library genuinely lacks the answer — say so).

Never invent citations. Every claim about a paper must trace to a note, a
highlight, or the PDF. When you use a paper, link it as `[[note-name]]`.

## Tools (all read Zotero read-only via immutable sqlite; safe while Zotero runs)

    python3 tools/zotero_read.py stats|collections
    python3 tools/zotero_read.py list [--collection NAME] [--since DATE] [--limit N]
    python3 tools/zotero_read.py item KEY            # full dump + highlights + notes
    python3 tools/zotero_read.py search "query"
    python3 tools/lit_note.py sync KEY... | sync-all | topics | path KEY
    python3 tools/fetch.py [--dry-run] [--top N] [--source arxiv|s2|both]
    python3 tools/feedback.py keep|drop <id> [--zotero --collection NAME]
    python3 tools/s2_graph.py ARXIV_ID [--citations N]          # lineage + frontier
    python3 tools/zotero_add.py ARXIV_ID [--collection NAME]   # connector: item + PDF, auto-routes to Recommend
    python3 tools/viz.py [--date YYYY-MM-DD] [--open]          # interactive knowledge-graph HTML

`fetch.py` recalls from arXiv (today's newest) + Semantic Scholar recommendations
(seeded by the library; set `S2_API_KEY` env for higher rate limits). Logic lives
in `tools/paperlib.py`. Per-source quotas (`top_arxiv`, `top_s2` in
`.interests.yaml`) keep daily freshness from being crowded out by recommendations;
already-surfaced papers are tracked in `Inbox/.surfaced.txt` and never repeated.
fetch.py also writes a machine-readable `Inbox/.last_fetch.json`.

`viz.py` builds `Daily/<date>-graph.html` — a self-contained force-directed graph
linking each fetched paper to the user's interest **areas** and to the specific
**library papers it shares concepts with** (edges form only on specific sub-concepts
like latent action / WAM / tactile / representation-for-action — broad terms like
VLA/world-model are area-level only, so the graph isn't "everything connects").
Clicking a paper shows its problem / innovation / potential directions (from
`Inbox/.digest.json`, written by the `/papers digest` step) plus the abstract.
`viz.py --serve [--port 8765]` runs a local server where the detail panel's
👍/👎/➕ buttons call `feedback.py keep/drop` and `zotero_add.py` live — feedback in
the graph steers future recommendations. Each paper card also has a **🔬 deep read**
button: it fetches the paper's arXiv HTML full text and runs the user's 6-section
method-analysis template (`Research/paper-reading-template.md`) via `claude -p`,
rendering the Chinese analysis into the card and caching it in `Inbox/.digest.json`
under `deep`. No external deps.

`zotero_add.py` uses the Zotero **connector** (Settings → Advanced → "Allow other
applications…"). It saves the item AND uploads the real PDF as a stored attachment
via a two-step saveItems→saveAttachment flow (the connector won't fetch the PDF on
its own outside a browser), then calls `/updateSession` to **auto-route the item
into a fixed collection (default `Recommend`)** — no manual click in the Zotero UI
needed. Override with `--collection NAME`, or `--no-collection` to use the current
UI selection.

`rg`/Grep over `Literature/` and `Topics/` is usually the fastest way to find
which notes are relevant to a question — search titles, highlights, and the
user's synthesis at once.

## Core workflows

### Answer a research question (the main job)
1. `rg -l -i "<terms>" Literature/ Topics/` to find candidate notes; widen terms
   if thin. Also `zotero_read.py search` for library items without notes yet.
2. Read the most relevant notes (highlights first). Pull PDF text only if needed.
3. Synthesize across papers: agreements, contradictions, lineage, gaps. Ground
   every point in a `[[note]]` and quote the user's highlight when relevant.
4. End with the 3–5 most relevant `[[notes]]` and any obvious next reads.

### Read / digest a specific paper
1. Resolve it: `zotero_read.py search` or by `[[note]]`. `lit_note.py sync KEY`
   to refresh the note from Zotero first.
2. **Default = deep read** in the user's 6-section structure (see
   `Research/paper-reading-template.md`): 摘要翻译 · 方法动机 · 方法设计(最细致) ·
   与其他方法对比(创新点三段式 + 对比表) · 实验 · 学习与应用 · 总结(核心一句话 +
   第一性原理问句 + 速记 pipeline). Read the PDF, stay **method-focused**, Chinese,
   weave in the user's highlights. "简要" → short problem/method/result/neighbours.
3. Offer to write a draft into the note's **Synthesis** section (ask first; edit
   only below the marker line).

### Fetch new papers (scheduled daily 07:00, or on demand)
1. `python3 tools/fetch.py` — writes ranked stubs to `Inbox/` in two buckets
   (fresh arXiv + S2 recommendations). Append a summary to `Daily/<today>.md`.
2. Report top picks with one-line "why relevant" each, grouped by the user's
   areas. Do **not** auto-add to Zotero; let the user triage in `Inbox/`.
3. Record reactions: `feedback.py keep <id>` / `drop <id>`. This is how the
   fetcher learns.

### Keep the vault in sync
- New/changed papers in Zotero: `lit_note.py sync-all` then `lit_note.py topics`.
- This is idempotent and preserves every user-written section.

## Slash commands (`.claude/commands/`) — 4 hubs, each dispatches on its first word
- **`/papers [fetch|digest|triage|keep <id>|drop <id>]`** — the daily paper flow.
  `fetch` (default) pulls new papers (arXiv + S2) → `Inbox/`; `digest` writes the
  prioritized reading plan **and** the interactive value graph (headless 07:00);
  `triage` reviews the batch with **clickable** 👍/👎 (AskUserQuestion →
  `feedback.py keep/drop`); `keep`/`drop` teach the fetcher directly (keep can also
  `zotero_add.py` the PDF).
- **`/ask <q | paper | connect [theme]>`** — library Q&A. A question → grounded
  answer; an arXiv id / `[[note]]` / `paper: <title>` → digest + citation lineage;
  `connect [theme]` → surface missed links across the vault.
- **`/research [gaps|ideas|weekly]`** — synthesis & ideation. `gaps` mines open
  problems; `ideas` proposes novel directions (idea-generation + novelty-assessment);
  `weekly` is the weekly synthesis (headless Sun 07:30). Outputs land under `Research/`.
- **`/sync-vault`** — refresh notes + Topic MOCs from Zotero.

When presenting fetched papers, prefer collecting reactions via AskUserQuestion
(clickable) over asking the user to type ids.

## Evolving with the user (important)

This agent is meant to track the user's interests as they shift. The profile
adapts through several channels — use them actively:

- **Automatic:** every fetch re-learns keywords from the Zotero library
  (highlighted papers weighted higher) and re-seeds S2 recommendations from it.
  So just by adding/highlighting papers, the user steers the agent.
- **Triage feedback:** `feedback.py keep/drop` — kept ids become S2 seeds,
  dropped ids become negative signals. Encourage quick keep/drop reactions.
- **Conversational (you do this):** when the user expresses an interest shift in
  chat — "I'm getting into spatial intelligence", "less pure-CV please", "stop
  showing me X" — **edit `.interests.yaml`**: add/raise a `boost` term, add a
  `mute` term, or add an `arxiv_category`. Make the smallest change that captures
  it, tell the user what you changed, and keep the "Your research areas" comment
  block current. Treat `.interests.yaml` as a living profile, not static config.
- When you notice a recurring theme in what the user asks about that isn't in the
  profile yet, suggest adding it.

Current focus (keep this in sync with `.interests.yaml`): embodied foundation
models (WAM, VLA); tactile / contact-rich manipulation; multimodal LLMs, vision
foundation models, spatial intelligence; the embodied-AI-relevant parts of LLMs.

## Conventions
- Respond in the user's language (they write Chinese; mixed technical English ok).
- Be concrete and cite. "I don't have a paper on X in your library" is a valid,
  useful answer — don't pad with general knowledge dressed up as their library.
- Keep scripts stdlib-only and read-only toward Zotero unless explicitly adding.
