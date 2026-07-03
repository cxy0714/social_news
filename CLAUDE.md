# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A **daily news digest pipeline**, not an application. There is no build/test/lint
cycle and no server. The "product" is the set of markdown files under `digests/`,
produced by Claude itself (web search/fetch) on a cloud schedule and committed to
git. State persists *only* through committed files — each cloud run is a fresh
clone with no memory, so **every run must `git add . && git commit && git push`**
or its work is lost.

Two distinct execution modes exist; know which one you are in:

1. **Cloud scheduled task (primary).** Claude runs on Anthropic's cloud nightly,
   uses its *own* `web_search`/`web_fetch` to survey newspapers, writes the
   digest, and pushes. It does **not** run `fetch_news.py`. The authoritative
   spec for this mode is `instruction.md` — read it before generating any digest.
2. **Local helper.** `scripts/fetch_news.py` runs on a user's own machine (no
   cloud egress restrictions) to pre-fetch RSS candidates. Claude then classifies
   and summarizes those candidates into a digest.

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
