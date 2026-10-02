# 更新日志 · Changelog

本项目所有值得记录的变更都写在这里。

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
按日期分组，条目分为**新增 / 变更 / 修复 / 移除**四类。日常新闻 digest 的产出
不逐条记录（每天都有），只记录管线、网页层与调研层本身的演进。所有日期为北京时间。

## [2026-10-02]

### 变更
- LLM 后端收敛为**一条容灾链**，统一由 `llm_client.chat_json()` 执行：主用**上海交大
  网关**的 DeepSeek（`DEEPSEEK_API_BASE=https://models.sjtu.edu.cn/api/v1`），不可用时
  自动降级到 **DeepSeek 官方 API**（`.env` 的 `LLM_PROVIDERS=deepseek,deepseek-official`）。
- 每周综述此前只能固定用单个 provider，现在与每日 digest 共用同一条链；两者都可用
  `--provider` 临时只跑一个后端（新增 `deepseek-official` 取值）。
- 重试改为**轮转**：每轮把链上每个可用 provider 各试一次，所以主用端挂了最多等一个
  `LLM_TIMEOUT` 就切备用端，短暂抖动仍能靠后续轮次恢复。
- digest / 周报里的模型标注带上实际端点（如 `deepseek@sjtu:deepseek-chat`），便于事后
  核对那一期到底是谁生成的。

### 新增
- `.env` 新增备用端点三项 `DEEPSEEK_OFFICIAL_API_BASE / _API_KEY / _MODEL`；留占位符或
  不填会被自动跳过并在日志里提示，不算错误。备用腿模型名用官方的 **`deepseek-flash`**
  （V4.1 Flash，官方 `/models` 当前只列 `deepseek-flash` 与 `deepseek-v4-pro`；旧名
  `deepseek-chat` 已被路由到 flash）。主用腿仍是网关上的 `deepseek-chat`——交大网关并没有
  flash 型号（写 flash 会 403）。
- 模型测评（`scripts/build_eval.py`）支持**两个方向**：`--fresh-provider {claude,deepseek,
  deepseek-official}` 指定哪一栏现跑（复用方自动归到另一栏、标签按其 digest 头如实标注），
  `--from-raw` 让现跑方复用 `digests/_raw-DATE.md`，两栏吃**同一份材料**、差异只来自模型。
  首次产出 `evals/2026-10-02.md`：同一份 594 条候选，官方 `deepseek-flash` vs Claude。

### 修复
- 模型测评（`build_eval.py`）的 Claude 栏改为**显式指定** `providers=["claude"]`，否则会
  被新的默认容灾链（交大网关 → 官方）覆盖，测的就不再是 Claude 了。

## [2026-07-10]

### 新增
- 网页层收藏（watchlist）改为**纯 token 登录**：GitHub token 仅存浏览器
  localStorage，构建脚本不接触 Gist、不消耗 token。
- 未登录访客可见**只读的公开 watchlist 快照**，内联进 `index.html`。

## [2026-07-09]

### 新增
- 上线**未来技术调研层**（`future-tech/`）：从新闻收藏一条深挖，产出七段式
  结构化调研报告并归档为 markdown。
- 待调研 watchlist 接入**私密 GitHub Gist**，站内每条新闻旁的 ☆ 按钮通过
  GitHub API 读写。
- 补齐 2026-07-08、2026-07-09 两期每日 digest。

## [2026-07-07]

### 新增
- 扩充 RSS 来源列表（`scripts/fetch_news.py` 的 `FEEDS`）。

## [2026-07-04]

### 变更
- 网页层重构为**单个自包含 `site/index.html`**（所有内容内联），本地
  `file://` 打开即可，放弃 GitHub Pages 部署。

### 修复
- `fetch_news.py` 强制 UTF-8 stdout，修复 Windows GBK 控制台下报告乱码/报错。

## [2026-07-03]

### 新增
- 首次引入**静态网页阅读层**：阅读器、更新日志、统计页。

### 移除
- 下线成就页（achievements）。

## [2026-07-01]

### 新增
- 新增来源媒体指南 `sources.md`，各来源附类型 / 立场 / 领域。

### 变更
- `sources.md` 中所有缩写展开为完整英文名。

## [2026-06-30]

### 新增
- 首期**每周综述**（weekly review）。
- 新增本地 RSS 预抓取脚本 `scripts/fetch_news.py`（仅标准库）。

## [2026-06-29]

### 新增
- 项目初始化：首期每日社会新闻 digest，覆盖五大类。
- 新增 **📚 概念观察** 栏目。
