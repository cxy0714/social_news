# web/ — 网页渲染层

把 `digests/*.md` 预编译成一个静态站点，托管在 GitHub Pages。**markdown 始终是
唯一事实来源**；这一层只做渲染，坏了也不影响 digest 本身，云端定时任务一行都不用改。

## 站点结构

| 页面 | 内容 |
|------|------|
| `index.html` / `home.html` | 首页：项目介绍 + 最新一期卡片 + 统计概览 |
| `2026-07-03.html` 等 | 每篇 digest 一个独立页，带日期侧栏（每日 / 每周两个 tab） |
| `changelog.html` | 更新日志，从 git 提交历史自动生成 |
| `stats.html` | 统计：逐期产量（条目/链接/字数/候选），可选 token 用量 |

顶部导航：首页 / 每日 / 每周 / 更新 / 统计。日期侧栏用 tab 分「每日 Daily」和
「每周 Weekly」两组。

## 本地构建

```bash
pip install markdown          # 唯一依赖，标准库之外只需这个
python web/build.py           # -> site/（gitignore，不入库）
python web/build.py --out DIR # 自定义输出目录
```

构建产物 `site/` 不入库——由 GitHub Actions（`.github/workflows/pages.yml`）在
push 时自动构建并部署。本地跑只是为了预览。

预览：直接用浏览器打开 `site/index.html` 即可（纯静态，无需起服务器）。

## 自动部署

`.github/workflows/pages.yml` 在 `digests/**`、`web/**` 或工作流自身变动时触发：
装 `markdown` → 跑 `build.py` → 部署到 Pages。

**一次性配置（在 GitHub 仓库里手动开）：**
1. Settings → Pages → Source 选 **GitHub Actions**。
2. 仓库需为 Public（或有 Pages 权限的私有仓库）。

## 组成

- `build.py` — 构建脚本（纯 Python 标准库 + `markdown`）
- `templates/page.html` — digest 页模板（带日期侧栏）
- `templates/standalone.html` — 首页 / changelog / stats 模板（全宽）
- `static/style.css` — 明暗主题、CJK 排版、移动端适配
- `static/app.js` — 主题切换、侧栏 tab、移动端抽屉

## 统计与 token

见 [`../stats/README.md`](../stats/README.md)。简言之：产量指标构建时直接数出，
token 用量需可选的 `stats/usage.jsonl`（构建脚本本身不消耗 token）。
