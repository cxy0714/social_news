# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A **daily news digest pipeline**, not an application. There is no build/test/lint
cycle and no server. The "product" is the set of markdown files under `digests/`,
produced by Claude itself (web search/fetch) on a cloud schedule and committed to
git. State persists *only* through committed files — each cloud run is a fresh
clone with no memory, so **every run must `git add . && git commit && git push`**
or its work is lost.

Three distinct execution modes exist; know which one you are in:

1. **Cloud scheduled task (primary).** Claude runs on Anthropic's cloud nightly,
   uses its *own* `web_search`/`web_fetch` to survey newspapers, writes the
   digest, and pushes. It does **not** run `fetch_news.py`. The authoritative
   spec for this mode is `instruction.md` — read it before generating any digest.
2. **Local helper.** `scripts/fetch_news.py` runs on a user's own machine (no
   cloud egress restrictions) to pre-fetch RSS candidates. Claude then classifies
   and summarizes those candidates into a digest.
3. **Local API pipeline (自动无人值守).** `scripts/generate_digest.py` runs
   end-to-end on the user's Windows machine via a scheduled task: RSS candidates
   → fetch public article bodies (in-memory, LLM context only) → an LLM
   (DeepSeek by default, or Claude — switched via `LLM_PROVIDER` in `.env`)
   classifies/dedupes/summarizes → renders the `instruction.md` §3 template →
   writes `digests/YYYY-MM-DD.md`, updates the README index, optionally
   commits/pushes. This is the "定时任务用 API" mode. Copyright rules (§2) still
   hold: fetched bodies are never written to the digest or committed; paywalled
   hosts (`PAYWALL_HOSTS`) use RSS headline/blurb only. Config lives in `.env`
   (gitignored); see `.env.example` and `scripts/README.md`. `git_commit_push`
   runs `git pull --rebase --autostash` **before** push so the local machine and
   the cloud task can share one repo without non-fast-forward rejections.

   **Scheduling.** `scripts/setup_task.ps1` registers **two** tasks, both running
   `scripts/run_daily.ps1`: `social-news-daily` at `-Time` (default **06:00**),
   and `social-news-boot` at logon + `-BootDelayMin` (default **2**) minutes — the
   latter catches up after the PC was off for days. `run_daily.ps1` always runs in
   **catch-up mode**: `generate_digest.py --catch-up --lookback N` (default N=3)
   backfills any missing `digests/YYYY-MM-DD.md` in the last N days (today + past
   days), fetching RSS once and filtering per Beijing-day window; days whose RSS
   has already rolled out of the window yield no candidates and are skipped. Then,
   on success, `generate_weekly.py --catch-up` backfills any completed ISO week
   (Sunday ≤ today) missing its `digests/weekly-YYYY-MM-DD.md` — synthesized from
   that week's daily digests (no fresh RSS fetch), Sunday-dated, README weekly
   index updated. Both tasks are idempotent: an already-present day/week is
   skipped. The `.ps1` wrappers are stored **UTF-8 with BOM**: the scheduled
   task's Windows PowerShell 5.1 reads BOM-less files as GBK and fails to parse
   the Chinese comments.

## Producing a digest (the core task)

Follow `instruction.md` §1 (每日工作流). In short:

- Survey the sources listed in `instruction.md` §4 for the last ~24h.
- Cover **five categories**: 政治·国际 / 经济·财经 / 科技 / 社会·民生 / 灾害·突发
  (~3–8 high-value items each), dedupe across sources, tag each with a `region`.
- Write `digests/YYYY-MM-DD.md` using the template in `instruction.md` §3
  (sectioned **by category**, region as a per-item source tag).
- Update the "最近 7 天" index at the top of `README.md`.
- Commit and push.

### Copyright rules (hard constraints — see `instruction.md` §2)

- Write only **original short summaries** (中文, ≤50 字) + **always link the
  source**. Never copy source paragraphs; any direct quote < 15 words, once.
- Do not bypass paywalls (WSJ/FT/Economist etc.) — use public headlines/blurbs.
- Label official wire services (新华社/TASS/etc.) vs. independent media faithfully;
  do not editorialize.
- If a source is unreachable, skip it and note `本日未覆盖: …` at the file end.

## Local RSS helper

```bash
python3 scripts/fetch_news.py              # past 24h → digests/_raw-YYYY-MM-DD.md
python3 scripts/fetch_news.py --hours 48   # widen window
python3 scripts/fetch_news.py --out PATH   # custom output
```

- Standard library only (Python 3.9+); no pip install. Supports both RSS
  (`<item>`) and Atom (`<entry>`).
- Fetches **title/link/time/source only — never article bodies** (copyright).
- Output `digests/_raw-*.md` is a gitignored intermediate; the real deliverable
  is still `digests/YYYY-MM-DD.md`, which Claude writes from these candidates.
- Add/remove sources by editing the `FEEDS` list at the top of the script,
  as `(name, region, RSS_URL)` tuples.

## 输出风格

本项目**不要精简输出**。摘要、分类说明、覆盖情况都用完整表述——即使全局启用了 terse/精简模式,在本仓库也保持正常散文,不要压缩成词组或片段。

## 未来技术调研层（future-tech/）

一个独立于每日 digest 的产出：从新闻里**收藏**一条值得深挖的（多为科技类），以它
为起点写一篇**结构化深度调研报告**，归档进 `future-tech/YYYY-MM-DD-<slug>.md`。

- **报告**是入库的 markdown，格式见 `future-tech/README.md`（七段式：核心结论 / 技术
  原理 / 关键玩家 / 现状进展 / 挑战争议 / 未来时间线 / 延伸阅读）。版权红线同 §2：
  只写原创综述 + 必附来源链接，不复制原文、不绕过付费墙。
- **待调研 watchlist** 不入库——存在用户的私密 GitHub Gist（`watchlist.json`）。站点
  里每条新闻旁的 ☆ 按钮通过 GitHub API 读写该 Gist；Gist ID/token 仅存浏览器
  localStorage。`web/build.py` 渲染 `#future` 落地页与各报告视图，watchlist 由 `app.js`
  运行时从 Gist 拉取，构建脚本不碰 Gist、不消耗 token。
- 云端定时任务不涉及这一层；报告由用户在交互会话里请求生成（"从这条写一篇未来技术
  调研"）。

## 模型测评层（evals/）

又一个独立产出：同一天的每日 digest 用**不同模型**各生成一版并排对比（当前 DeepSeek
vs Claude），观察分类粒度、去重合并、摘要笔法与「概念观察」的抽取差异。

- **产出**是入库 markdown `evals/YYYY-MM-DD.md`，格式见 `evals/README.md`：两大段
  `## 🟦 DeepSeek` / `## 🟩 Claude`，各自内部是降一级的五大类分区 + 概念观察。
- 生成脚本 `scripts/build_eval.py`：DeepSeek 方**复用**当天 `digests/YYYY-MM-DD.md`
  正文（省一次调用），Claude 方按 `generate_digest.py` 同一流水线现抓候选重跑；两个
  provider 的 key 都要在 `.env` 就绪。版权红线同 §2。
- `web/build.py` 渲染 `#eval` 落地页与各对比视图（topnav「模型测评 Eval」tab）。
  云端定时任务不涉及这一层。

## Conventions

- All times/dates use **Beijing time (北京时间)**; digest filenames are `YYYY-MM-DD`.
- **Digest files themselves stay pure markdown — no HTML inside `digests/`.** The
  web layer under `web/` renders those markdown files into a single self-contained
  `site/index.html` (gitignored) that the user opens/bookmarks locally via
  `file://` — the repo is private, so there is no GitHub Pages deploy. Markdown
  remains the single source of truth; the cloud task still only writes markdown
  and never runs the web build. See `web/README.md`.
- Cloud runs may be limited to `claude/`-prefixed branches unless the repo has
  "Allow unrestricted branch pushes" enabled (see `instruction.md` §0).

## 网页层（web/）

- `digests/*.md` 是唯一事实来源；`web/build.py` 只做渲染，**不消耗 token**、不改动
  digest。它把所有 digest、CSS、JS 内联进单个 `site/index.html`，用户本地浏览器
  打开/收藏即可（私有仓库，无 GitHub Pages）。云端定时任务无需运行它。改站点
  样式/结构只动 `web/`，绝不为了网页去改 digest markdown 格式。
- 统计页的 token 用量来自可选的 `stats/usage.jsonl`（见 `stats/README.md`）；产量
  指标由构建脚本直接从 digest 统计。
