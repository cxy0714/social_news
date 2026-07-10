#!/usr/bin/env python3
"""本地 API 版·端到端生成每日 digest（零第三方依赖）。

流水线：RSS 抓候选 → 抓公开正文（喂 LLM 用，不入库）→ LLM 分类去重+中文摘要
→ 渲染成 instruction.md §3 模板 → 写 digests/YYYY-MM-DD.md + 更新 README →
可选 git commit & push。

与云端 Claude 本体模式并存：本脚本是「本地 Windows 计划任务」用的，靠 DeepSeek/
Claude 的 HTTP API（provider 见 .env）。守 instruction.md §2 版权红线：抓来的正文
**只在内存里喂给 LLM**，产出仍是原创中文摘要(≤50字)+链接；付费墙站点只用 RSS 公开
标题/摘要，不抓正文。

用法：
    python3 scripts/generate_digest.py                 # 今天，过去 24h，不 commit
    python3 scripts/generate_digest.py --hours 48
    python3 scripts/generate_digest.py --commit        # 生成后 add/commit/push
    python3 scripts/generate_digest.py --dry-run       # 只抓候选、不调 LLM、不落盘
    python3 scripts/generate_digest.py --max-items 100 # 喂给 LLM 的候选上限

仅标准库，Python 3.9+。
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
import urllib.error
from html.parser import HTMLParser
from pathlib import Path

import fetch_news
import llm_client

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

ROOT = Path(__file__).resolve().parent.parent
DIGESTS = ROOT / "digests"
README = ROOT / "README.md"

BEIJING = dt.timezone(dt.timedelta(hours=8))

# 付费墙 / 强反爬站点：只用 RSS 公开标题+摘要，绝不抓正文（版权红线）。
PAYWALL_HOSTS = (
    "wsj.com", "ft.com", "economist.com", "bloomberg.com", "nytimes.com",
    "thetimes.co.uk", "nikkei.com", "caixin.com",
)

CATEGORIES = ["政治 · 国际", "经济 · 财经", "科技", "社会 · 民生", "灾害 · 突发"]


class _TextExtractor(HTMLParser):
    """极简正文提取：收集 <p> 里的可见文本，跳过 script/style。"""

    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self._in_p = 0
        self.chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style", "nav", "header", "footer", "aside"):
            self._skip += 1
        elif tag == "p":
            self._in_p += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "nav", "header", "footer", "aside"):
            self._skip = max(0, self._skip - 1)
        elif tag == "p":
            self._in_p = max(0, self._in_p - 1)

    def handle_data(self, data: str) -> None:
        if self._skip == 0 and self._in_p > 0:
            t = data.strip()
            if t:
                self.chunks.append(t)


def is_paywalled(url: str) -> bool:
    return any(h in url for h in PAYWALL_HOSTS)


def fetch_body(url: str, limit: int = 600) -> str:
    """抓公开正文摘录（仅喂 LLM 理解，不入库）。付费墙直接返回空串。"""
    if is_paywalled(url):
        return ""
    try:
        raw = fetch_news.fetch(url)  # 复用带 UA/超时的抓取
    except (urllib.error.URLError, TimeoutError, Exception):  # noqa: BLE001
        return ""
    try:
        html_text = raw.decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return ""
    parser = _TextExtractor()
    try:
        parser.feed(html_text)
    except Exception:  # noqa: BLE001
        return ""
    text = re.sub(r"\s+", " ", " ".join(parser.chunks)).strip()
    return text[:limit]


def collect_candidates(hours: int, max_items: int) -> tuple[list[dict], list[str]]:
    """跑 RSS，去重，返回候选列表 + 不可达来源名列表。"""
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    seen: set[str] = set()
    items: list[dict] = []
    unreachable: list[str] = []
    for name, region, url in fetch_news.FEEDS:
        try:
            raw = fetch_news.fetch(url)
            found = fetch_news.extract_items(raw)
        except Exception:  # noqa: BLE001
            unreachable.append(name)
            continue
        for it in found:
            when = it.get("when")
            if when is not None and when < cutoff:
                continue
            key = fetch_news.norm_title(it["title"])
            if not key or key in seen:
                continue
            seen.add(key)
            it["source"], it["region"] = name, region
            items.append(it)
    items = items[:max_items]
    return items, unreachable


SYSTEM_PROMPT = """\
你是一名严谨的新闻编辑，为「学习宏观经济学与社会学的中文读者」编写每日新闻摘要。
你会收到一批候选新闻（标题 / 来源 / 地区 / 可能的公开正文摘录）。任务：

1. 按五大类分组：政治·国际 / 经济·财经 / 科技 / 社会·民生 / 灾害·突发。每类保留约
   3-8 条高价值条目（社会类可多些），过滤体育娱乐花边。
2. 同一事件多源时**合并为一条**，主摘要选信息最全者，并在 reports 里列出所有报道该
   事件的媒体链接（不要只留一个而丢掉其他家）。
3. 每条写：中文小标题（title）；≤50 字的原创中文摘要（summary，用自己的话，绝不复制
   原文段落）；region 地区标签（如 中东/欧洲/北美/中国大陆/亚太 等）。
4. 概念观察：从当日真实条目里抽 3 个宏观经济学概念 + 3 个社会学概念，每个给中英文名、
   一句定义、以及对应的当日新闻和挂靠理由。要从真实条目出发，不硬套。

严格输出**一个 JSON 对象**，结构：
{
  "categories": [
    {"name": "政治 · 国际", "items": [
      {"title": "中文小标题", "summary": "≤50字中文摘要", "region": "中东",
       "reports": [{"source": "BBC", "url": "https://..."}]}
    ]}
  ],
  "macro": [{"term_zh": "成本推动型通胀", "term_en": "Cost-push inflation",
             "definition": "一句定义", "news": "对应的新闻小标题", "why": "挂靠理由"}],
  "socio": [{"term_zh": "风险社会", "term_en": "Risk society",
             "definition": "一句定义", "news": "对应新闻", "why": "挂靠理由"}]
}
name 必须用上述五个类目原文。reports 至少一条、URL 用候选里给的原始链接。只输出 JSON。"""


def build_user_payload(items: list[dict], date_str: str) -> str:
    lines = [f"日期（北京时间）：{date_str}", f"候选新闻共 {len(items)} 条：", ""]
    for i, it in enumerate(items, 1):
        body = it.get("body", "")
        lines.append(f"[{i}] {it['title']}")
        lines.append(f"    来源: {it['source']} | 地区: {it['region']} | 链接: {it['link']}")
        if body:
            lines.append(f"    正文摘录: {body}")
    return "\n".join(lines)


def _fmt_reports(reports: list[dict]) -> str:
    links = [f"[{r.get('source', '来源')}]({r.get('url', '')})"
             for r in reports if r.get("url")]
    return f"📎 报道({len(links)})：" + " · ".join(links)


def render_body(data: dict) -> str:
    """五大类分区 + 概念观察正文（不含 H1 标题 / front-matter / 尾注）。

    eval 对比栏目复用它，把两个 provider 的正文并排堆叠。"""
    out: list[str] = []
    by_name = {c.get("name", ""): c.get("items", []) for c in data.get("categories", [])}
    for cat in CATEGORIES:
        out.append(f"## {cat}")
        rows = by_name.get(cat, [])
        if not rows:
            out.append("- （本类今日无高价值条目）")
        for it in rows:
            region = it.get("region", "")
            tag = f" `{region}`" if region else ""
            out.append(f"- **{it.get('title', '（无标题）')}** — {it.get('summary', '')}{tag}")
            out.append(f"  {_fmt_reports(it.get('reports', []))}")
        out.append("")
    out.append(_render_concepts(data))
    return "\n".join(out)


def render_digest(data: dict, date_str: str, kept: int, hours: int,
                  unreachable: list[str]) -> str:
    label = llm_client.model_label()
    out = [f"# 每日新闻摘要 · {date_str}",
           f"> 生成时间：{date_str}（北京时间）",
           "> 类型：政治·国际 / 经济·财经 / 科技 / 社会·民生 / 灾害·突发",
           f"> 采集方式：本地 `scripts/generate_digest.py` 抓公开 RSS（过去约 {hours} "
           f"小时，{kept} 条候选），由 {label} 分类去重+中文摘要。抓来的正文仅用于理解，"
           "未复制入库。", "", render_body(data), "", "---",
           "_说明：摘要均为原创概述并附原文链接，未复制原文。同一事件合并为一条并列"
           "出全部报道来源。来源如实标注，不做立场加工。_"]
    if unreachable:
        out.append(f"_本日未覆盖：{', '.join(unreachable)}（RSS 返回错误或超时，已跳过）。_")
    return "\n".join(out) + "\n"


def _render_concepts(data: dict) -> str:
    lines = ["---", "## 📚 概念观察 · 宏观经济学 & 社会学",
             "> 给学习宏观经济学与社会学的读者：从今日新闻抽取核心概念 + 现实案例。", "",
             "### 宏观经济学"]
    for c in data.get("macro", []):
        lines.append(f"- **{c.get('term_zh','')}（{c.get('term_en','')}）** — "
                     f"{c.get('definition','')}📰 对应：*{c.get('news','')}*——{c.get('why','')}")
    lines.append("")
    lines.append("### 社会学")
    for c in data.get("socio", []):
        lines.append(f"- **{c.get('term_zh','')}（{c.get('term_en','')}）** — "
                     f"{c.get('definition','')}📰 对应：*{c.get('news','')}*——{c.get('why','')}")
    return "\n".join(lines)


def update_readme(date_str: str) -> None:
    """把今天插入 README「最近 7 天」索引顶部，去重，保留最近 7 条。"""
    if not README.exists():
        return
    text = README.read_text(encoding="utf-8")
    marker = "## 最近 7 天"
    if marker not in text:
        return
    head, _, tail = text.partition(marker)
    # tail 形如 "\n\n- [2026-07-09](...)\n- ...\n\n---\n..."
    rest_split = tail.split("\n---", 1)
    body = rest_split[0]
    footer = "\n---" + rest_split[1] if len(rest_split) > 1 else ""
    dates = re.findall(r"\[(\d{4}-\d{2}-\d{2})\]", body)
    merged = [date_str] + [d for d in dates if d != date_str]
    merged = merged[:7]
    new_body = "\n\n" + "\n".join(
        f"- [{d}](./digests/{d}.md)" for d in merged) + "\n"
    README.write_text(head + marker + new_body + footer, encoding="utf-8")


def git_commit_push(date_str: str) -> None:
    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)

    run("add", "digests", "README.md")
    staged = run("diff", "--cached", "--quiet")
    if staged.returncode == 0:
        print("（无改动可提交，跳过 commit）")
        return
    r = run("commit", "-m", f"news: {date_str}")
    if r.returncode != 0:
        print(f"⚠ commit 失败：{r.stderr.strip()}")
        return
    p = run("push")
    if p.returncode != 0:
        print(f"⚠ push 失败（已本地 commit）：{p.stderr.strip()}")
    else:
        print("✅ 已 commit 并 push")


def main() -> int:
    ap = argparse.ArgumentParser(description="本地 API 版每日 digest 生成")
    ap.add_argument("--hours", type=int, default=24, help="RSS 回溯窗口（默认 24）")
    ap.add_argument("--max-items", type=int, default=120, help="喂给 LLM 的候选上限")
    ap.add_argument("--date", default=None, help="覆盖日期 YYYY-MM-DD（默认今天北京时间）")
    ap.add_argument("--commit", action="store_true", help="生成后 git add/commit/push")
    ap.add_argument("--dry-run", action="store_true", help="只抓候选，不调 LLM、不落盘")
    ap.add_argument("--no-body", action="store_true", help="不抓正文，仅用标题分类摘要")
    ap.add_argument("--provider", choices=["deepseek", "claude"], default=None,
                    help="覆盖 .env 的 LLM_PROVIDER（本次运行用哪个模型）")
    ap.add_argument("--out", default=None, help="覆盖输出路径（默认 digests/YYYY-MM-DD.md）")
    args = ap.parse_args()

    llm_client.load_dotenv()
    if args.provider:
        import os
        os.environ["LLM_PROVIDER"] = args.provider
    date_str = args.date or dt.datetime.now(BEIJING).strftime("%Y-%m-%d")

    print(f"→ 抓取 RSS 候选（过去 {args.hours}h）…")
    items, unreachable = collect_candidates(args.hours, args.max_items)
    print(f"  候选 {len(items)} 条；不可达源 {len(unreachable)} 个：{', '.join(unreachable) or '无'}")

    if args.dry_run:
        for it in items[:20]:
            print(f"  - [{it['source']}] {it['title']}")
        print(f"\n(dry-run) 共 {len(items)} 条候选，未调 LLM。")
        return 0
    return _generate(args, items, unreachable, date_str)


def _generate(args, items: list[dict], unreachable: list[str], date_str: str) -> int:
    if not items:
        print("⚠ 没有候选，终止。")
        return 1

    if not args.no_body:
        print("→ 抓取公开正文摘录（仅喂 LLM，不入库）…")
        for it in items:
            it["body"] = fetch_body(it["link"])

    print(f"→ 调用 LLM（{llm_client.model_label()}）分类去重+摘要…")
    try:
        data = llm_client.chat_json(SYSTEM_PROMPT, build_user_payload(items, date_str))
    except llm_client.LLMError as e:
        print(f"✗ {e}")
        return 1

    md = render_digest(data, date_str, len(items), args.hours, unreachable)
    out_path = Path(args.out) if args.out else DIGESTS / f"{date_str}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    try:
        print(f"✅ 已写入 {out_path.relative_to(ROOT)}")
    except ValueError:
        print(f"✅ 已写入 {out_path}")

    # 只有写正式 digest（未自定义 --out）时才更新 README 索引。
    if not args.out:
        update_readme(date_str)
        print("✅ 已更新 README「最近 7 天」索引")

    if args.commit:
        git_commit_push(date_str)
    else:
        print("（未加 --commit，未提交 git）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
