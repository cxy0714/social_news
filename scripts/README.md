# 本地抓取脚本

> 用于在**你自己的电脑**上跑（本地网络无云端出口限制），补足云端定时任务抓不到的源。

## fetch_news.py — RSS 新闻抓取

巡视主流媒体公开 RSS，筛选过去 N 小时条目、去重，生成「原始候选清单」markdown。
**只用 Python 标准库，无需 pip 安装任何东西**（Python 3.9+）。

```bash
# 默认过去 24 小时，输出 digests/_raw-YYYY-MM-DD.md
python3 scripts/fetch_news.py

# 放宽到 48 小时
python3 scripts/fetch_news.py --hours 48

# 自定义输出路径
python3 scripts/fetch_news.py --out /tmp/news.md
```

跑完终端会列出**每个源取到/保留多少条**，方便你看哪些 RSS 本地可用、哪些失效。

### 工作流（推荐）

```
本地: python3 scripts/fetch_news.py        # 抓 RSS → 候选清单
  ↓
Claude Code: 「读 digests/_raw-今天.md，做五类分类+中文摘要，写成 digests/今天.md 并 commit」
```

脚本只负责**抓取/去重/过滤**（标题/链接/时间，不抓正文，守版权）；
**分类与中文摘要交给 Claude**，质量更好也更省事。

### 设计原则
- 只用公开 RSS，只取标题/链接/时间/来源，不抓正文全文（版权红线）。
- 带浏览器 UA、超时、源间隔；失败源自动跳过并在报告中标注。
- 不解析复杂 HTML、不绕过付费墙、不对抗反爬。

### 增删源
编辑 `fetch_news.py` 顶部的 `FEEDS` 列表，按 `(媒体名, 区域, RSS_URL)` 增删即可。
没有 RSS 的站点（很多大陆媒体、付费墙站）暂不在本脚本范围内。

### 备注
`digests/_raw-*.md` 是本地中间产物，已在 `.gitignore` 中忽略，不会污染仓库。
正式的每日 digest 仍是 `digests/YYYY-MM-DD.md`。
