#!/usr/bin/env python3
"""
本地新闻抓取脚本（RSS 优先，零第三方依赖）。

用途：在你自己的电脑上跑（本地网络无云端出口墙），巡视主流媒体的公开 RSS，
筛选过去 N 小时的条目、去重，生成一份「原始候选清单」markdown。
随后可：(a) 在 Claude Code 里让它读这份清单做分类+中文摘要+落盘；
或 (b) 后续给本脚本接 Anthropic API 自动摘要。

设计原则（守住版权与礼貌爬取）：
- 只用公开 RSS，只取 标题/链接/时间/来源，**不抓正文全文**。
- 带浏览器 UA、超时、源间隔；失败的源跳过并在报告里标注。
- 不解析复杂 HTML，不绕过付费墙、不对抗反爬。

用法：
    python3 scripts/fetch_news.py                # 默认过去 24 小时
    python3 scripts/fetch_news.py --hours 48     # 放宽到 48 小时
    python3 scripts/fetch_news.py --out digests/_raw-2026-06-29.md

仅标准库，Python 3.9+ 即可运行。
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
import time
import urllib.error
import urllib.request
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

# ── 源清单：(媒体名, 区域, RSS URL) ──────────────────────────────────────────
# 这些都是公开 RSS。本地大多可直接取到；个别站点 RSS 可能失效，脚本会自动跳过并报告。
FEEDS: list[tuple[str, str, str]] = [
    # 北美
    ("NPR",                 "北美", "https://feeds.npr.org/1001/rss.xml"),
    ("CBC News",            "北美", "https://www.cbc.ca/webfeed/rss/rss-topstories"),
    ("The New York Times",  "北美", "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"),
    ("The Washington Post", "北美", "https://feeds.washingtonpost.com/rss/national"),
    ("USA Today",           "北美", "https://www.usatoday.com/rss"),
    # 欧洲
    ("BBC News",            "欧洲", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("The Guardian",        "欧洲", "https://www.theguardian.com/world/rss"),
    ("Le Monde",            "欧洲", "https://www.lemonde.fr/rss/une.xml"),
    ("Der Spiegel Intl",    "欧洲", "https://www.spiegel.de/international/index.rss"),
    # 亚太 / 港澳台
    ("Al Jazeera",          "亚太/中东", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("The Japan Times",     "亚太", "https://www.japantimes.co.jp/feed/"),
    ("South China Morning Post", "港澳台", "https://www.scmp.com/rss/91/feed"),
    # 中国大陆（公开 RSS 多已停用，能取到算赚到；取不到属正常）
    ("人民网",              "中国大陆", "http://www.people.com.cn/rss/politics.xml"),
    ("中国新闻网",          "中国大陆", "https://www.chinanews.com.cn/rss/scroll-news.xml"),
]

UA = ("Mozilla/5.0 (compatible; SocialNewsDigest/1.0; +https://github.com/) "
      "Python-urllib news-digest")
TIMEOUT = 15          # 单源超时（秒）
POLITE_DELAY = 1.0    # 源之间间隔（秒），礼貌爬取


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        "Accept-Language": "en,zh-CN;q=0.8,zh;q=0.7",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def parse_when(text: str | None) -> dt.datetime | None:
    """解析 RSS(RFC822) 或 Atom(ISO8601) 时间，返回带时区的 datetime。"""
    if not text:
        return None
    text = text.strip()
    # RSS pubDate: "Sun, 28 Jun 2026 14:30:00 GMT"
    try:
        d = parsedate_to_datetime(text)
        if d is not None:
            return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        pass
    # Atom: "2026-06-28T14:30:00Z" / "...+00:00"
    try:
        d = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1]  # 去掉 XML 命名空间前缀


def extract_items(xml: bytes) -> list[dict]:
    """同时支持 RSS(<item>) 与 Atom(<entry>)。"""
    items: list[dict] = []
    root = ET.fromstring(xml)
    nodes = [e for e in root.iter() if strip_ns(e.tag) in ("item", "entry")]
    for node in nodes:
        title = link = when = None
        for child in node:
            t = strip_ns(child.tag)
            if t == "title" and child.text:
                title = child.text.strip()
            elif t == "link":
                # RSS: 文本即链接；Atom: href 属性
                link = (child.text or "").strip() or child.attrib.get("href", "").strip() or link
            elif t in ("pubDate", "published", "updated", "date") and child.text:
                when = when or child.text.strip()
        if title and link:
            items.append({"title": title, "link": link, "when": parse_when(when)})
    return items


def norm_title(title: str) -> str:
    """归一化标题用于去重：小写、去标点、压空白。"""
    s = re.sub(r"[\W_]+", " ", title.lower(), flags=re.UNICODE)
    return s.strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="本地 RSS 新闻抓取 → 候选清单 markdown")
    ap.add_argument("--hours", type=int, default=24, help="保留过去 N 小时内的条目（默认 24）")
    today = dt.date.today().isoformat()
    ap.add_argument("--out", default=f"digests/_raw-{today}.md", help="输出文件路径")
    ap.add_argument("--no-dedup", action="store_true",
                    help="不按标题去重，保留所有条目（含跨源近似重复）")
    args = ap.parse_args()

    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=args.hours)
    by_region: dict[str, list[dict]] = {}
    seen: set[str] = set()
    report: list[str] = []
    total_kept = 0

    for name, region, url in FEEDS:
        try:
            raw = fetch(url)
            items = extract_items(raw)
        except (urllib.error.URLError, ET.ParseError, Exception) as e:  # noqa: BLE001
            report.append(f"  ✗ {name:<22} 失败：{type(e).__name__}: {e}")
            time.sleep(POLITE_DELAY)
            continue

        kept = 0
        for it in items:
            when = it["when"]
            # 没有时间的条目：保守保留（很多源不带时间），但不参与超时过滤
            if when is not None and when < cutoff:
                continue
            key = norm_title(it["title"])
            if not key:
                continue
            if not args.no_dedup:
                if key in seen:
                    continue
                seen.add(key)
            it["source"] = name
            by_region.setdefault(region, []).append(it)
            kept += 1
        total_kept += kept
        report.append(f"  ✓ {name:<22} 取到 {len(items):>3} 条，保留 {kept:>3} 条")
        time.sleep(POLITE_DELAY)

    # ── 写候选清单 ──────────────────────────────────────────────────────────
    lines: list[str] = []
    lines.append(f"# 新闻候选清单（原始）· {today}")
    _dedup_note = "未去重" if args.no_dedup else "去重后"
    lines.append(f"> 本地 RSS 抓取，过去 {args.hours} 小时，{_dedup_note}共 {total_kept} 条。")
    lines.append("> 下一步：在 Claude Code 里让它读本文件，做分类(政治/经济/科技/社会/灾害)+中文摘要，写成正式 digest。")
    lines.append("")
    for region in ("北美", "欧洲", "亚太", "亚太/中东", "港澳台", "中国大陆", "其他"):
        rows = by_region.get(region)
        if not rows:
            continue
        rows.sort(key=lambda r: (r["when"] is None, r["when"] or cutoff), reverse=True)
        lines.append(f"## {region}（{len(rows)}）")
        for r in rows:
            ts = r["when"].astimezone().strftime("%m-%d %H:%M") if r["when"] else "时间未知"
            lines.append(f"- [{r['title']}]({r['link']}) — `{r['source']}` · {ts}")
        lines.append("")

    out_path = args.out
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # ── 终端报告 ────────────────────────────────────────────────────────────
    print("源抓取情况：")
    print("\n".join(report))
    print(f"\n✅ 共保留 {total_kept} 条（已去重），已写入：{out_path}")
    print("   下一步：在 Claude Code 里说「读 " + out_path + " 做分类和中文摘要，生成今天的 digest」")
    return 0


if __name__ == "__main__":
    sys.exit(main())
