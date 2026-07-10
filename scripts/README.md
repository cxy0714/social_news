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

---

## fetch_guardian.py — 按日期「真·回溯」一周

RSS 只缓存最新条目，抓不到一周前的旧闻。本脚本走 **The Guardian Open Platform API**，
可按日期范围检索全 archive，因此能拿到「真正的一周」。同样**只用标准库**、只取
标题/链接/时间/栏目（不抓正文，守版权）。

**前置（一次性）**：在 https://open-platform.theguardian.com/access/ 免费申请 key（即时发放到邮箱），然后设环境变量：

```powershell
# Windows PowerShell
$env:GUARDIAN_API_KEY = "你的key"
```
```bash
# Bash
export GUARDIAN_API_KEY="你的key"
```

**用法**：

```bash
python3 scripts/fetch_guardian.py                          # 默认过去 7 天
python3 scripts/fetch_guardian.py --days 7
python3 scripts/fetch_guardian.py --from 2026-06-23 --to 2026-06-30
python3 scripts/fetch_guardian.py --out digests/_raw-guardian-2026-06-30.md
```

默认只保留硬新闻栏目（World/Business/Tech/Environment/Society 等），过滤体育娱乐花边；
要调整在脚本顶部 `KEEP_SECTIONS` 改即可。输出与 `fetch_news.py` 同构，可与 RSS 候选合并后交给 Claude 分类摘要。

> 想要**多源**真历史：可类比再加 NYT Article Search API，或用 GDELT（免费、回溯多年、一接口多源）。Guardian 一家已能覆盖政治/经济/世界/环境/社会，足够撑起每周综述的回溯部分。

---

## generate_digest.py — 本地 API 版·端到端生成 digest

与云端 Claude 本体模式并存的**第三种执行方式**：在你自己的电脑上，用脚本一条龙跑完
「RSS 抓候选 → 抓公开正文喂 LLM → LLM 分类去重+中文摘要 → 写 `digests/YYYY-MM-DD.md`
+ 更新 README → 可选 commit/push」。LLM 后端可在 **DeepSeek**（默认，官方或交大网关）
和 **Claude**（Anthropic 官方 API）之间切换。**仅标准库**（`urllib` + `html.parser`）。

**一次性配置**：把根目录 `.env.example` 复制为 `.env`，填 provider 与 key：

```bash
cp .env.example .env      # 然后编辑：LLM_PROVIDER / *_API_KEY / *_MODEL
```

**用法**：

```bash
python3 scripts/generate_digest.py                 # 今天，过去 24h，不 commit
python3 scripts/generate_digest.py --hours 48
python3 scripts/generate_digest.py --commit        # 生成后自动 add/commit/push
python3 scripts/generate_digest.py --dry-run       # 只抓候选、不调 LLM、不落盘（省钱自检）
python3 scripts/generate_digest.py --no-body       # 不抓正文，仅用标题（更快更省 token）
python3 scripts/generate_digest.py --max-items 100 # 喂给 LLM 的候选上限
```

### 版权红线（同 instruction.md §2）
- 抓来的正文**只在内存里喂给 LLM 做理解**，产出仍是原创中文摘要(≤50字)+链接，
  **正文绝不写进 digest、绝不 commit**。
- 付费墙 / 强反爬站点（WSJ/FT/经济学人/Bloomberg/NYT 等，见脚本 `PAYWALL_HOSTS`）
  **只用 RSS 公开标题+摘要，不抓正文**。

### Windows 计划任务（无人值守）

```powershell
# 1) 先手动验证一次（不提交）
powershell -ExecutionPolicy Bypass -File scripts\run_daily.ps1 -NoCommit

# 2) 注册每天定时任务（默认 07:30，自动 commit/push）
powershell -ExecutionPolicy Bypass -File scripts\setup_task.ps1 -Time 07:30

# 立即触发一次 / 删除任务
Start-ScheduledTask -TaskName social-news-daily
powershell -ExecutionPolicy Bypass -File scripts\setup_task.ps1 -Remove
```

- `run_daily.ps1`：wrapper，自动选 `.venv` 或 PATH 上的 python，运行主脚本并把输出
  写进 `logs/digest-YYYY-MM-DD.log`（`logs/` 已 gitignore）。
- `setup_task.ps1`：注册/删除计划任务，`-StartWhenAvailable` 让关机错过后开机补跑。
- **交大网关**（`https://models.sjtu.edu.cn/api/v1`）只在校园网/内网可达，正因如此本模式
  跑在本地而非云端。

### llm_client.py
provider 抽象层：`chat_json(system, user) -> dict`，内部封装 DeepSeek（OpenAI 兼容
`/chat/completions`）与 Claude（`/v1/messages`）的差异，带超时/重试/JSON 抽取；另含极简
`load_dotenv()`。切 provider 只改 `.env` 里的 `LLM_PROVIDER`，脚本无需改动。
