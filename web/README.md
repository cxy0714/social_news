# web/ — 网页渲染层

把 `digests/*.md` 编译成**一个自包含的 `site/index.html`**——所有 CSS、JS、每期
digest 全部内联进这一个文件。**markdown 始终是唯一事实来源**；这一层只做渲染，
坏了也不影响 digest 本身，云端定时任务一行都不用改。

仓库是私有的，不走 GitHub Pages。查看方式：本地跑一次 `build.py`，用浏览器打开
（或收藏）生成的 `site/index.html`，双击 `file://` 即可，纯离线、无需起服务器。
每次重新构建都原地覆盖同一个文件，收藏不会失效。

## 单文件结构

页面之间不再是多个 HTML，而是同一文档里的多个 `<section data-view="…">`，靠 URL
hash（`#2026-07-03`、`#stats` 等）客户端切换，只显示当前一个：

| 视图 | 内容 |
|------|------|
| `#home`（默认） | 首页：项目介绍 + 最新一期卡片 + 统计概览 |
| `#2026-07-03` 等 | 每篇 digest 一个视图，带日期侧栏（每日 / 每周两个 tab） |
| `#future` | 未来技术：待调研 watchlist（读自 Gist）+ 调研报告卡片 |
| `#ft-2026-07-09-vertical-farming` 等 | 每篇未来技术调研报告一个视图 |
| `#changelog` | 更新日志，从 git 提交历史自动生成 |
| `#stats` | 统计：逐期产量（条目/链接/字数/候选），可选 token 用量 |

顶部导航：首页 / 每日 / 每周 / 未来技术 / 来源 / 更新 / 统计。

## 未来技术层与收藏（Gist）

- `#future` 视图渲染 `future-tech/*.md` 报告为卡片；每篇报告另有独立视图。
- 每条新闻条目旁有 **☆ 收藏按钮**（`app.js` 运行时注入），点击把该条写入你的一个
  **私密 GitHub Gist**（`watchlist.json`）。Gist ID 与 token 存在浏览器 localStorage，
  **绝不入库**；在 `#future` 页点「⚙ 设置 Gist」配置。读 Gist 免 token，写需 `gist`
  权限的 token。纯 `file://` 可用（GitHub API 支持跨域）。详见 `future-tech/README.md`。digest 之间在 markdown 里的相对链接
（如 `[..](./2026-07-01-full.md)`）由构建脚本在渲染时改写成对应的 `#hash`，页内
跳转直接生效——digest markdown 本身不改。

## 本地构建与查看

```bash
pip install markdown          # 唯一依赖，标准库之外只需这个
python web/build.py           # -> site/index.html（gitignore，不入库）
python web/build.py --out DIR # 自定义输出目录
```

构建产物 `site/index.html` 不入库。首次生成后用浏览器打开并收藏这个本地文件，
之后每次 `python web/build.py` 覆盖它、刷新浏览器即可看到新一期。

## 组成

- `build.py` — 构建脚本（纯 Python 标准库 + `markdown`），输出单个内联 HTML
- `static/style.css` — 明暗主题、CJK 排版、移动端适配（构建时内联）
- `static/app.js` — hash 路由（视图切换）、主题切换、侧栏 tab、移动端抽屉（构建时内联）

`static/` 下两个文件是**源文件**，供构建时读取并内联进 `index.html`；单文件产物
里不再引用它们，因此也不必随产物一起分发。

## 统计与 token

见 [`../stats/README.md`](../stats/README.md)。简言之：产量指标构建时直接数出，
token 用量需可选的 `stats/usage.jsonl`（构建脚本本身不消耗 token）。
