# 📚🛰️ Research Agent · 科研论文智能体

把你的 **Zotero 文献库**变成一个每天**自动追新论文、按你口味排序、逐篇讲解、并基于你自己的库回答问题**的科研助手——所有结果以一张可交互的「宇宙星空」知识图谱呈现。

由 [Claude Code](https://www.anthropic.com/claude-code) 或 [OpenAI Codex](https://developers.openai.com/codex) 驱动，外加几个**零依赖的 Python 脚本**（纯标准库，无需 `pip install`）。**只读**访问 Zotero，绝不改动你的库。

📖 中文 ·  [English](README.en.md)

![交互知识图谱](docs/graph.png)

*交互知识图谱（`tools/viz.py --serve`）：今天推荐的论文连到你的兴趣**领域**和库中**相关论文**，背景是缓缓旋转的星系。点任意论文看价值卡片、生成**深度精读**、并排查看**原版 PDF**、用 **👍 / 👎 / ➕** 调教推荐。*

> 不熟悉这些工具？**Zotero** = 免费文献管理器（你的论文库）；**Obsidian** = 免费 Markdown 笔记软件（可选）；**Claude Code / Codex** = 命令行 AI 智能体。你需要 Zotero ＋ 其中一个智能体即可。

---

## ✨ 能做什么

- 🛰️ **每日追新** — 从 arXiv（最新）+ Semantic Scholar（按你库推荐）拉论文，按你的兴趣打分排序，自动和已有的去重。
- 🃏 **自动价值卡片** — 每篇生成「解决的问题 / 创新点 / 潜在方向」。
- 🌌 **交互知识图谱** — 自包含网页，论文连到你的兴趣领域和库中相关论文；可看卡片、生成精读、并排原版 PDF、点赞/点踩调教推荐。
- 💬 **基于你的库问答** — 答案引用你自己的笔记和高亮，绝不编造。
- 🔬 **深度精读** — 任意论文的 6 段式方法分析（动机/设计/对比/实验/复现/总结）。
- 🧭 **科研综合** — 挖掘开放问题、生成新点子、每周综述。
- 🎯 **越用越懂你** — 反馈 + 你在 Zotero 的高亮，持续调整推荐方向。

## 🧰 前置条件

| 需要 | 用途 | 说明 |
|---|---|---|
| **Python 3.9+** | 跑脚本 | 纯标准库，无需安装任何包 |
| **Zotero 7+** | 你的文献库 | 免费桌面应用 · <https://www.zotero.org> |
| **Claude Code** 或 **OpenAI Codex** | 智能体（问答/卡片/精读） | 二选一，见[下文](#-选择智能体claude-code-或-codex) |
| Obsidian（可选） | 更舒服地读笔记 | <https://obsidian.md> |

> 想把论文**保存进 Zotero**（含 PDF）时，需开启：Zotero → 设置 → 高级 → 勾选「允许其他应用与 Zotero 通信」。只读你的库**不需要**这一步。

## 🚀 快速开始

```bash
# 1. 克隆
git clone https://github.com/hengcaoai-cloud/awesome-research-agent.git ~/Paper
cd ~/Paper

# 2.（可选）指定 Zotero 位置（默认 ~/Zotero）
export ZOTERO_DIR="$HOME/Zotero"

# 3. 一键初始化（检查依赖 + 从 Zotero 生成笔记）
bash tools/setup.sh

# 4. 拉今天的论文 + 自动生成价值卡片
python3 tools/fetch.py
python3 tools/digest_cards.py        # 需要 Claude Code 或 Codex

# 5. 打开交互知识图谱（含 👍/👎、PDF、深度精读）
python3 tools/viz.py --serve          # → http://127.0.0.1:8765
```

然后在项目目录里运行智能体：

```bash
cd ~/Paper && claude         # 或：codex
# 试试：  /papers          抓取并整理今天的论文
#         /ask 世界模型有哪些开放问题？
```

> 用 **Obsidian** 打开 `~/Paper` 即可浏览 `Literature/`、`Topics/`（带反链与关系图）。

## 🕹️ 四个核心命令

| 命令 | 作用 |
|---|---|
| `/papers [fetch｜digest｜triage｜keep <id>｜drop <id>]` | 每日论文流：抓取 → 价值卡片＋图谱 → 一键反馈；`keep`/`drop` 调教推荐 |
| `/ask <问题 ｜ 某篇论文 ｜ connect [主题]>` | 基于库问答 / 精读单篇（含引用脉络）/ 找跨论文关联 |
| `/research [gaps｜ideas｜weekly]` | 挖开放问题 · 出新点子 · 每周综述（存到 `Research/`） |
| `/sync-vault` | 从 Zotero 重建笔记与主题地图 |

## 🤖 选择智能体：Claude Code 或 Codex

两者皆可，用 `RESEARCH_AGENT_LLM` 切换，其余功能完全一致。

- **Claude Code（默认）**：无需设置。指令在 `CLAUDE.md`，命令在 `.claude/commands/`。
- **OpenAI Codex**：
  ```bash
  export RESEARCH_AGENT_LLM=codex
  mkdir -p ~/.codex/prompts && ln -s "$PWD/.claude/commands/"*.md ~/.codex/prompts/
  codex                                # 在项目目录里运行
  ```
  Codex 读取 `AGENTS.md`（已附带，镜像 `CLAUDE.md`）。

## ⏰ 每天自动跑（可选）

- **macOS**：`bash tools/install_schedule.sh`（每天 07:00 ＋ 周日 07:30；`--uninstall` 卸载）
- **Linux**：`crontab -e` 加一行
  ```
  0 7 * * *  cd $HOME/Paper && PAPER_AGENT_LLM=1 /bin/bash tools/daily.sh
  ```

## ⚙️ 配置

- **`.interests.yaml`** — 调你的兴趣：`boost` 加权关键词、`mute` 屏蔽词、`arxiv_categories`、配额（`top_arxiv`/`top_s2`/`min_score`）。每次抓取还会**自动从你的库学习**（高亮过的论文权重更高），所以只要在 Zotero 读和高亮就能引导它。
- **环境变量**：`ZOTERO_DIR`（Zotero 位置）、`S2_API_KEY`（可选，更好的推荐）、`RESEARCH_AGENT_LLM`（`claude`／`codex`）。

## 🗂️ 目录结构

```
Paper/
├── CLAUDE.md / AGENTS.md  # 智能体指令（Claude Code / Codex）
├── .interests.yaml        # 你的兴趣画像（改我）
├── tools/                 # 全部 Python 工具（纯标准库）+ 脚本
├── .claude/commands/      # 4 个 slash 命令
├── Literature/  Topics/   # 论文笔记 / 主题地图（自动生成）
├── Inbox/  Daily/         # 待筛论文 + 状态 / 每日日志与图谱（自动生成）
└── Research/              # gaps / ideas / weekly 输出（自动生成）
```

`Literature/ Topics/ Inbox/ Daily/ Research/` 是**你的个人数据**，已被 `.gitignore` 排除——克隆是空的，用起来才填充。

## 🔐 隐私与安全

- **Zotero 只读**：以 `immutable` 模式打开 `zotero.sqlite`，绝不写入（Zotero 开着也安全）。
- **保存**论文是唯一的写操作，且经 Zotero 官方连接器、由你授权。
- 图谱服务只绑定 **`127.0.0.1`**（仅本机）。
- `.gitignore` 默认把你的笔记、PDF、状态都挡在 git 之外。

## 📄 License

MIT，见 [LICENSE](LICENSE)。基于 [Claude Code](https://www.anthropic.com/claude-code) / [Codex](https://developers.openai.com/codex)、[Zotero](https://www.zotero.org)、[arXiv](https://arxiv.org)、[Semantic Scholar](https://www.semanticscholar.org)。
