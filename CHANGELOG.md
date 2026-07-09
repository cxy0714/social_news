# 更新日志 · Changelog

本项目所有值得记录的变更都写在这里。

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
按日期分组，条目分为**新增 / 变更 / 修复 / 移除**四类。日常新闻 digest 的产出
不逐条记录（每天都有），只记录管线、网页层与调研层本身的演进。所有日期为北京时间。

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
