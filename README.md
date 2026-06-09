<div align="center">

# 📚🛰️ Research Agent · 科研论文智能体

**把你的 Zotero 文献库，变成每天自动追新、按你口味排序、逐篇讲解、还能基于你自己的库问答的科研助手。**

![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)
![deps](https://img.shields.io/badge/依赖-零（纯标准库）-4c9a2a)
![agent](https://img.shields.io/badge/智能体-Claude%20Code%20｜%20Codex-8a5cf6)
![Zotero](https://img.shields.io/badge/Zotero-只读-CC2936?logo=zotero&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-2e7d32)

📖 中文 ·  [English](README.en.md)

</div>

![交互知识图谱](docs/graph.png)

> 所有结果汇成一张可交互的「宇宙星空」知识图谱：今天推荐的论文连到你的兴趣**领域**和库中**相关论文**。点一下就能看价值卡片、生成**深度精读**、并排原版 **PDF**、**搜索整个文献库**、👍/👎 调教推荐。由 [Claude Code](https://www.anthropic.com/claude-code) 或 [OpenAI Codex](https://developers.openai.com/codex) 驱动，纯 Python 零依赖，**只读**访问 Zotero。

## ✨ 功能

| | |
|---|---|
| 🛰️ **每日追新** | arXiv + Semantic Scholar，按你的兴趣打分排序、自动去重 |
| 🃏 **价值卡片** | 每篇自动生成「问题 / 创新点 / 潜在方向」 |
| 🌌 **交互图谱** | 论文连到你的领域和相关论文，可视化整个研究版图 |
| 🔎 **内置库搜索＋笔记阅读** | 网页里搜全库、读摘要和你的高亮、点 `[[双链]]` 跳转、看反向链接——**无需 Obsidian** |
| 💬 **基于你的库问答** | 答案引用你自己的笔记和高亮，绝不编造 |
| 🔬 **深度精读** | 任意论文的 6 段式方法分析 |
| 🎯 **越用越懂你** | 反馈 + 你的 Zotero 高亮，持续调整推荐 |

## 🚀 上手（一条命令）

**前置**：Python 3.9+ · Zotero 7+ · [Claude Code](https://www.anthropic.com/claude-code) 或 [Codex](https://developers.openai.com/codex) 之一。

```bash
git clone https://github.com/hengcaoai-cloud/awesome-research-agent.git ~/Paper
cd ~/Paper
bash start.sh            # 一键完成全部，并打开图谱
```

`start.sh` 会自动：①（首次）检查依赖 + 从你的 Zotero 生成笔记 → ② 拉取今天的论文 → ③ 生成价值卡片 → ④ 在浏览器打开知识图谱 <http://127.0.0.1:8765>。**以后每天就这一条命令。**

> Zotero 不在默认位置？先 `export ZOTERO_DIR="你的Zotero文件夹"` 再运行。

想用智能体**问答**，在项目目录里运行：

```bash
cd ~/Paper && claude            # 或：codex
#  /papers              抓取并整理今天的论文
#  /ask 世界模型有哪些开放问题？
```

## 🕹️ 四个命令

| 命令 | 作用 |
|---|---|
| `/papers` | 每日论文流：抓取 → 价值卡片＋图谱 → 反馈（`keep`/`drop` 调教推荐） |
| `/ask <问题｜论文｜connect 主题>` | 基于库问答 / 精读单篇 / 找跨论文关联 |
| `/research <gaps｜ideas｜weekly>` | 挖开放问题 · 出新点子 · 每周综述 |
| `/sync-vault` | 从 Zotero 重建笔记 |

## 🤖 用 Claude Code 还是 Codex

二选一，用 `RESEARCH_AGENT_LLM` 切换，其余完全一致：

```bash
# 默认 Claude Code，无需设置。改用 Codex：
export RESEARCH_AGENT_LLM=codex
mkdir -p ~/.codex/prompts && ln -s "$PWD/.claude/commands/"*.md ~/.codex/prompts/
```

Claude Code 读 `CLAUDE.md`，Codex 读 `AGENTS.md`（已附带）。

## ⚙️ 配置 & 自动化

- **`.interests.yaml`** — 调你的兴趣（加权/屏蔽关键词、类别）。每次抓取还会自动从你库里学习（高亮过的权重更高）。
- **环境变量** — `ZOTERO_DIR`（Zotero 位置，默认 `~/Zotero`）、`S2_API_KEY`（可选，更好的推荐）。
- **每天自动跑** — macOS：`bash tools/install_schedule.sh`；Linux：把 `tools/daily.sh` 加进 `crontab`。

## 🔐 隐私

**Zotero 全程只读**（绝不改你的库）· 图谱服务只绑定本机 `127.0.0.1` · `.gitignore` 默认把你的笔记/PDF/状态全部挡在 git 之外。

## 📄 License

MIT，见 [LICENSE](LICENSE)。基于 Claude Code / Codex、[Zotero](https://www.zotero.org)、[arXiv](https://arxiv.org)、[Semantic Scholar](https://www.semanticscholar.org)。
