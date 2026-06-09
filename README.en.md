# 📚🛰️ Research Agent

Turn your **Zotero** library into a research assistant that **fetches new papers
daily, ranks them to your taste, explains each one, and answers questions grounded
in your own library** — all shown as an interactive "galaxy" knowledge graph.

Powered by [Claude Code](https://www.anthropic.com/claude-code) or
[OpenAI Codex](https://developers.openai.com/codex), plus a few **dependency-free
Python scripts** (stdlib only — nothing to `pip install`). Your Zotero database is
read **read-only**; the agent never modifies it.

[中文](README.md) ·  📖 English

![Interactive knowledge graph](docs/graph.png)

*The interactive knowledge graph (`tools/viz.py --serve`): today's recommendations
linked to your interest **areas** and the **library papers** they share concepts
with, over an animated galaxy. Click any paper for its value card, a full **deep
read**, the original **PDF** side-by-side, and **👍 / 👎 / ➕** actions.*

> New to these tools? **Zotero** is a free reference manager (your paper library);
> **Obsidian** is a free Markdown notes app (optional); **Claude Code / Codex** are
> CLI AI agents. You need Zotero + one of the agents.

---

## ✨ Features

- 🛰️ **Daily recall** — newest relevant arXiv papers + Semantic Scholar recs seeded
  by *your* library, scored to your interests, deduped against what you have.
- 🃏 **Auto value cards** — *Problem / Innovation / Potential directions* per paper.
- 🌌 **Interactive graph** — papers linked to your interest **areas** and the
  specific **library papers** they share concepts with; value cards, deep reads,
  in-panel PDF, and 👍/👎 feedback that steers tomorrow's picks.
- 💬 **Grounded Q&A** — answers cited to your own notes and highlights, never invented.
- 🔬 **Deep reads** — a 6-section, method-focused analysis of any paper.
- 🧭 **Synthesis** — mine open problems, generate ideas, weekly digests.
- 🎯 **Learns your taste** — feedback + your Zotero highlights retune what it surfaces.

## 🧰 Requirements

| Need | For | Notes |
|---|---|---|
| **Python 3.9+** | runs the tools | stdlib only — no packages |
| **Zotero 7+** | your library | free desktop app · <https://www.zotero.org> |
| **Claude Code** or **OpenAI Codex** | the agent | pick one (see [below](#-choose-your-agent)) |
| Obsidian (optional) | nicer note reading | <https://obsidian.md> |

> To **save** papers into Zotero (with PDF), enable: Zotero → Settings → Advanced →
> "Allow other applications … to communicate with Zotero." Reading needs nothing.

## 🚀 Quick start

```bash
# 1. Clone
git clone https://github.com/hengcaoai-cloud/awesome-research-agent.git ~/Paper
cd ~/Paper

# 2. (optional) where Zotero lives (default ~/Zotero)
export ZOTERO_DIR="$HOME/Zotero"

# 3. Guided setup (checks prerequisites, builds notes from Zotero)
bash tools/setup.sh

# 4. Fetch today's papers + auto value cards
python3 tools/fetch.py
python3 tools/digest_cards.py        # needs Claude Code or Codex

# 5. Open the interactive graph (feedback + PDF + deep read)
python3 tools/viz.py --serve          # → http://127.0.0.1:8765
```

Then run the agent in the folder:

```bash
cd ~/Paper && claude        # or: codex
#  /papers          fetch + organize today's papers
#  /ask  what are the open problems in world models?
```

> Open `~/Paper` in **Obsidian** to browse `Literature/` and `Topics/` with backlinks.

## 🕹️ Four commands

| Command | What it does |
|---|---|
| `/papers [fetch｜digest｜triage｜keep <id>｜drop <id>]` | daily flow: fetch → value cards + graph → triage; `keep`/`drop` teach it |
| `/ask <question ｜ paper ｜ connect [theme]>` | grounded answer / digest one paper / find links |
| `/research [gaps｜ideas｜weekly]` | open problems · ideas · weekly digest (→ `Research/`) |
| `/sync-vault` | rebuild notes + topic maps from Zotero |

## 🤖 Choose your agent

Either works; switch with `RESEARCH_AGENT_LLM`. Everything else is identical.

- **Claude Code (default):** nothing to set. Instructions in `CLAUDE.md`, commands in
  `.claude/commands/`.
- **OpenAI Codex:**
  ```bash
  export RESEARCH_AGENT_LLM=codex
  mkdir -p ~/.codex/prompts && ln -s "$PWD/.claude/commands/"*.md ~/.codex/prompts/
  codex
  ```
  Codex reads `AGENTS.md` (shipped — mirrors `CLAUDE.md`).

## ⏰ Daily automation (optional)

- **macOS:** `bash tools/install_schedule.sh` (daily 07:00 + Sun 07:30; `--uninstall`)
- **Linux:** `crontab -e` →
  ```
  0 7 * * *  cd $HOME/Paper && PAPER_AGENT_LLM=1 /bin/bash tools/daily.sh
  ```

## ⚙️ Configuration

- **`.interests.yaml`** — tune `boost` keywords, `mute` terms, `arxiv_categories`,
  quotas. The fetcher also learns from your library each run (highlights weigh more).
- **Env vars:** `ZOTERO_DIR`, `S2_API_KEY` (optional, better recs),
  `RESEARCH_AGENT_LLM` (`claude` / `codex`).

## 🔐 Privacy & safety

- **Zotero is read-only** (opened with `immutable=1`; safe while Zotero runs).
- The graph server binds to **`127.0.0.1`** only.
- `.gitignore` keeps your notes, PDFs and state out of git — a clone starts empty.

## 📄 License

MIT — see [LICENSE](LICENSE). Built on
[Claude Code](https://www.anthropic.com/claude-code) /
[Codex](https://developers.openai.com/codex), [Zotero](https://www.zotero.org),
[arXiv](https://arxiv.org) and [Semantic Scholar](https://www.semanticscholar.org).
