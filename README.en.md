<div align="center">

# 📚🛰️ Research Agent

**Turn your Zotero library into a research assistant that fetches new papers daily, ranks them to your taste, explains each one, and answers questions grounded in your own library.**

![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)
![deps](https://img.shields.io/badge/dependencies-none%20(stdlib)-4c9a2a)
![agent](https://img.shields.io/badge/agent-Claude%20Code%20｜%20Codex-8a5cf6)
![Zotero](https://img.shields.io/badge/Zotero-read--only-CC2936?logo=zotero&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-2e7d32)

[中文](README.md) ·  📖 English

</div>

![Interactive knowledge graph](docs/graph.png)

> Everything lands in one interactive "galaxy" knowledge graph: today's recommendations linked to your interest **areas** and the **library papers** they share concepts with. Click for a value card, a full **deep read**, the original **PDF** side-by-side, full-text **library search**, and 👍/👎 feedback. Powered by [Claude Code](https://www.anthropic.com/claude-code) or [OpenAI Codex](https://developers.openai.com/codex), pure-Python with zero dependencies, **read-only** on Zotero.

## ✨ Features

| | |
|---|---|
| 🛰️ **Daily recall** | arXiv + Semantic Scholar, scored to your interests, auto-deduped |
| 🃏 **Value cards** | auto *Problem / Innovation / Directions* per paper |
| 🌌 **Interactive graph** | papers linked to your areas and related library papers |
| 🔎 **Built-in library search + reader** | search & read your notes/highlights and follow `[[links]]` — **no Obsidian needed** |
| 💬 **Grounded Q&A** | answers cited to your own notes and highlights, never invented |
| 🔬 **Deep reads** | a 6-section, method-focused analysis of any paper |
| 🎯 **Learns your taste** | feedback + your Zotero highlights retune what it surfaces |

## 🚀 Three steps

```bash
# 0. Needs Python 3.9+, Zotero 7+, and either Claude Code or Codex

git clone https://github.com/hengcaoai-cloud/awesome-research-agent.git ~/Paper && cd ~/Paper
bash tools/setup.sh                       # checks prerequisites + builds notes from Zotero
python3 tools/fetch.py && python3 tools/digest_cards.py   # fetch papers + value cards
python3 tools/viz.py --serve              # open the graph → http://127.0.0.1:8765
```

Then run the agent in the folder and chat:

```bash
cd ~/Paper && claude            # or: codex
#  /papers              fetch + organize today's papers
#  /ask  what are the open problems in world models?
```

## 🕹️ Four commands

| Command | What it does |
|---|---|
| `/papers` | daily flow: fetch → value cards + graph → feedback (`keep`/`drop` teach it) |
| `/ask <question｜paper｜connect theme>` | grounded answer / digest one paper / find links |
| `/research <gaps｜ideas｜weekly>` | open problems · ideas · weekly digest |
| `/sync-vault` | rebuild notes from Zotero |

## 🤖 Claude Code or Codex

Either works — switch with `RESEARCH_AGENT_LLM`; everything else is identical:

```bash
# Claude Code is the default. To use Codex instead:
export RESEARCH_AGENT_LLM=codex
mkdir -p ~/.codex/prompts && ln -s "$PWD/.claude/commands/"*.md ~/.codex/prompts/
```

Claude Code reads `CLAUDE.md`; Codex reads `AGENTS.md` (shipped).

## ⚙️ Config & automation

- **`.interests.yaml`** — tune boost/mute keywords & categories. The fetcher also learns from your library each run (highlights weigh more).
- **Env vars** — `ZOTERO_DIR` (default `~/Zotero`), `S2_API_KEY` (optional, better recs).
- **Daily job** — macOS: `bash tools/install_schedule.sh`; Linux: add `tools/daily.sh` to `crontab`.

## 🔐 Privacy

**Zotero is read-only** (never modified) · the graph server binds to `127.0.0.1` only · `.gitignore` keeps your notes, PDFs and state out of git.

## 📄 License

MIT — see [LICENSE](LICENSE). Built on Claude Code / Codex, [Zotero](https://www.zotero.org), [arXiv](https://arxiv.org) and [Semantic Scholar](https://www.semanticscholar.org).
