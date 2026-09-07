#!/usr/bin/env python3
"""
本地新闻抓取脚本（RSS + 公开列表页，零第三方依赖）。

用途：在你自己的电脑上跑（本地网络无云端出口墙），巡视主流媒体的公开 RSS / 公开列表页，
筛选过去 N 小时的条目、去重，生成一份「原始候选清单」markdown。
随后可：(a) 在 Claude Code 里让它读这份清单做分类+中文摘要+落盘；
或 (b) 后续给本脚本接 Anthropic API 自动摘要。

设计原则（守住版权与礼貌爬取）：
- 只用公开 RSS / 公开列表页，只取 标题/链接/时间/来源，**不抓正文全文**。
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
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from html import unescape
from email.utils import parsedate_to_datetime
from typing import Callable
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

# Route GFW-blocked Western RSS feeds through the local proxy. Domestic hosts
# (SJTU gateway, LLM relay, *.cn sources) stay direct. See proxy_setup.py.
try:
    from . import proxy_setup
except ImportError:  # 直接作为脚本运行时，回退到同目录导入
    import proxy_setup

proxy_setup.setup_proxy()


@dataclass(frozen=True)
class SourceSpec:
    name: str
    region: str
    url: str
    kind: str = "rss"
    parser: Callable[[str, str], list[dict]] | None = None

# ── 源清单：(媒体名, 区域, RSS URL) ──────────────────────────────────────────
# 这些都是公开 RSS / 公开列表页。本地大多可直接取到；个别站点可能失效，
# 脚本会自动跳过并报告。
FEEDS: list[tuple[str, str, str]] = [
    # 北美
    ("NPR",                 "北美", "https://feeds.npr.org/1001/rss.xml"),
    ("PBS NewsHour",        "北美", "https://www.pbs.org/newshour/feeds/rss/headlines"),
    ("The Washington Post", "北美", "https://feeds.washingtonpost.com/rss/national"),
    ("ProPublica",          "北美", "https://www.propublica.org/feeds/propublica/main"),
    ("The Conversation",    "全球", "https://theconversation.com/global/articles.atom"),
    # 欧洲
    ("BBC News",            "欧洲", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("The Guardian",        "欧洲", "https://www.theguardian.com/world/rss"),
    ("Le Monde",            "欧洲", "https://www.lemonde.fr/rss/une.xml"),
    ("Der Spiegel Intl",    "欧洲", "https://www.spiegel.de/international/index.rss"),
    ("Deutsche Welle",      "欧洲", "https://rss.dw.com/xml/rss-en-all"),
    ("France 24",           "欧洲", "https://www.france24.com/en/rss"),
    ("Bellingcat",          "欧洲", "https://www.bellingcat.com/feed/"),
    # 亚太 / 港澳台
    ("Al Jazeera",          "亚太/中东", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("The Japan Times",     "亚太", "https://www.japantimes.co.jp/feed/"),
    ("NHK World Japan",     "亚太", "https://www3.nhk.or.jp/rss/news/cat0.xml"),
    ("Yonhap News",         "亚太", "https://en.yna.co.kr/RSS/news.xml"),
    ("The Hindu",           "亚太", "https://www.thehindu.com/feeder/default.rss"),
    ("ABC News Australia",  "亚太", "https://www.abc.net.au/news/feed/51120/rss.xml"),
    ("CNA Singapore",       "亚太", "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml"),
    ("Nikkei Asia",         "亚太", "https://asia.nikkei.com/rss/feed/nar"),
    ("TechCrunch",          "北美", "https://techcrunch.com/feed/"),
    ("Ars Technica",        "北美", "https://feeds.arstechnica.com/arstechnica/index"),
    ("South China Morning Post", "港澳台", "https://www.scmp.com/rss/91/feed"),
    ("Hong Kong Free Press", "港澳台", "https://hongkongfp.com/feed/"),
    # 中国大陆（公开 RSS 多已停用；这次也补了几家公开列表页）
    ("人民网",              "中国大陆", "http://www.people.com.cn/rss/politics.xml"),
    ("中国新闻网",          "中国大陆", "https://www.chinanews.com.cn/rss/scroll-news.xml"),
]


def iter_sources() -> list[SourceSpec]:
    """返回全部可抓源：RSS + 公开列表页。"""
    return [
        *(SourceSpec(name, region, url) for name, region, url in FEEDS),
        SourceSpec("新华社", "中国大陆", "https://www.news.cn/", "html", parse_news_cn),
        SourceSpec("央视新闻", "中国大陆", "https://news.cctv.com/", "html", parse_cctv),
        SourceSpec("澎湃新闻", "中国大陆", "https://www.thepaper.cn/", "html", parse_thepaper),
        SourceSpec("财联社", "中国大陆", "https://www.cls.cn/", "html", parse_cls),
        SourceSpec("第一财经", "中国大陆", "https://www.yicai.com/", "html", parse_yicai),
        SourceSpec("界面新闻", "中国大陆", "https://www.jiemian.com/pro/lists/13.html", "html", parse_jiemian),
        SourceSpec("环球时报", "中国大陆", "https://world.huanqiu.com/", "html", parse_huanqiu),
    ]


BEIJING = dt.timezone(dt.timedelta(hours=8))

UA = ("Mozilla/5.0 (compatible; SocialNewsDigest/1.0; +https://github.com/) "
      "Python-urllib news-digest")
TIMEOUT = int(os.environ.get("RSS_TIMEOUT", "15"))  # 单源超时（秒）
POLITE_DELAY = 1.0    # 源之间间隔（秒），礼貌爬取


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        "Accept-Language": "en,zh-CN;q=0.8,zh;q=0.7",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def fetch_text(url: str) -> str:
    raw = fetch(url)
    for enc in ("utf-8", "gb18030", "gbk", "gb2312"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text)).strip()


def parse_beijing_date(text: str | None) -> dt.datetime | None:
    if not text:
        return None
    m = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text)
    if not m:
        return None
    try:
        return dt.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                           tzinfo=BEIJING)
    except ValueError:
        return None


def parse_compact_date(text: str | None) -> dt.datetime | None:
    if not text:
        return None
    m = re.search(r"(20\d{6})", text)
    if not m:
        return None
    try:
        return dt.datetime.strptime(m.group(1), "%Y%m%d").replace(tzinfo=BEIJING)
    except ValueError:
        return None


def parse_compact_timestamp(text: str | None) -> dt.datetime | None:
    if not text:
        return None
    m = re.search(r"(20\d{12})", text)
    if not m:
        return None
    try:
        return dt.datetime.strptime(m.group(1), "%Y%m%d%H%M%S").replace(tzinfo=BEIJING)
    except ValueError:
        return None


def parse_md_time(text: str | None, *, year: int | None = None) -> dt.datetime | None:
    if not text:
        return None
    m = re.search(r"(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})", text)
    if not m:
        return None
    y = year or dt.datetime.now(BEIJING).year
    try:
        return dt.datetime(y, int(m.group(1)), int(m.group(2)),
                           int(m.group(3)), int(m.group(4)), tzinfo=BEIJING)
    except ValueError:
        return None


def parse_hhmm(text: str | None, *, day: dt.date | None = None) -> dt.datetime | None:
    if not text:
        return None
    m = re.search(r"(\d{1,2}):(\d{2})", text)
    if not m:
        return None
    d = day or dt.datetime.now(BEIJING).date()
    try:
        return dt.datetime(d.year, d.month, d.day, int(m.group(1)), int(m.group(2)),
                           tzinfo=BEIJING)
    except ValueError:
        return None


def parse_epoch_ms(value: str | int | float | None) -> dt.datetime | None:
    if value in (None, ""):
        return None
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return None
    try:
        # 兼容毫秒时间戳（13 位）和秒时间戳（10 位）。
        ts = n / 1000 if abs(n) >= 10**12 else n
        return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def parse_url_date(url: str | None) -> dt.datetime | None:
    if not url:
        return None
    return parse_compact_date(url) or parse_beijing_date(url)


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


def _load_next_data(html_text: str) -> dict | None:
    m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(?P<data>.*?)</script>',
                  html_text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group("data"))
    except json.JSONDecodeError:
        return None


def _walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def parse_news_cn(html_text: str, base_url: str) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    patterns = [
        re.compile(r'<h1>\s*<a[^>]+href=[\'"](?P<link>https?://www\.news\.cn/[^\'"]+)[\'"][^>]*>(?P<title>.*?)</a>',
                   re.S),
        re.compile(r'<h3>\s*<a[^>]+href=[\'"](?P<link>https?://www\.news\.cn/[^\'"]+)[\'"][^>]*>(?P<title>.*?)</a>',
                   re.S),
        re.compile(r'<div class="tit"><a[^>]+href=[\'"](?P<link>https?://www\.news\.cn/[^\'"]+)[\'"][^>]*>(?P<title>.*?)</a>',
                   re.S),
    ]
    for pattern in patterns:
        for m in pattern.finditer(html_text):
            link = urljoin(base_url, m.group("link"))
            if "/20" not in link or "news.cn" not in link:
                continue
            if link in seen:
                continue
            title = clean_text(m.group("title"))
            if not title:
                continue
            seen.add(link)
            items.append({"title": title, "link": link, "when": parse_url_date(link)})
    return items


def parse_cctv(html_text: str, base_url: str) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    pattern = re.compile(
        r'<div class="silde(?: cur)?"[^>]*dataurl="(?P<dataurl>[^"]+)">.*?'
        r'<img[^>]*data-echo="(?P<img>[^"]+)".*?'
        r'<h3><a[^>]+href="(?P<link>[^"]+)"[^>]*>(?P<title>.*?)</a>',
        re.S,
    )
    for m in pattern.finditer(html_text):
        link = urljoin(base_url, m.group("link") or m.group("dataurl"))
        if link in seen:
            continue
        title = clean_text(m.group("title"))
        if not title:
            continue
        when = parse_compact_timestamp(m.group("img")) or parse_url_date(link)
        seen.add(link)
        items.append({"title": title, "link": link, "when": when})
    return items


def parse_thepaper(html_text: str, base_url: str) -> list[dict]:
    data = _load_next_data(html_text)
    if not data:
        return []
    items: list[dict] = []
    seen: set[str] = set()
    for node in _walk_json(data):
        if not isinstance(node, dict):
            continue
        title = node.get("name") or node.get("title")
        link = node.get("link") or node.get("url")
        when = node.get("pubTimeLong") or node.get("pubTime")
        if not title or not link or when is None:
            continue
        link = urljoin(base_url, str(link))
        if link in seen:
            continue
        seen.add(link)
        dt_when = parse_epoch_ms(when) or parse_beijing_date(str(when))
        items.append({"title": clean_text(str(title)), "link": link, "when": dt_when})
    return items


def parse_cls(html_text: str, base_url: str) -> list[dict]:
    data = _load_next_data(html_text)
    if not data:
        return []
    items: list[dict] = []
    seen: set[str] = set()
    for node in _walk_json(data):
        if not isinstance(node, dict):
            continue
        title = node.get("article_name") or node.get("title")
        if not title:
            continue
        link = node.get("article_jump") or node.get("article_url") or ""
        if isinstance(link, str) and link.startswith("cailianshe://"):
            link = ""
        if not link and node.get("article_id"):
            link = f"/detail/{node['article_id']}"
        if not link:
            continue
        link = urljoin(base_url, str(link))
        if not link.startswith("http") or link in seen:
            continue
        seen.add(link)
        when = parse_epoch_ms(node.get("article_time"))
        if when is None and node.get("article_date"):
            when = parse_beijing_date(str(node.get("article_date")))
        items.append({"title": clean_text(str(title)), "link": link, "when": when})
    return items


def parse_yicai(html_text: str, base_url: str) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    patterns = [
        re.compile(
            r'<div class="scrolfont" id="scrollFontDiv">.*?<li class="f-toe[^"]*">'
            r'<span>(?P<time>\d{1,2}:\d{2})</span><a href="(?P<link>[^"]+)"[^>]*>'
            r'<b>(?P<title>.*?)</b>',
            re.S,
        ),
        re.compile(
            r'<li class="card-list">.*?<img src="(?P<img>[^"]+)".*?'
            r'<h3 class="card-list__title">(?P<title>.*?)</h3>.*?'
            r'<span class="news-footer__date">\s*(?P<date>\d{2}/\d{2})\s*(?P<time>\d{2}:\d{2})\s*</span>',
            re.S,
        ),
    ]
    today = dt.datetime.now(BEIJING).date()
    for pattern in patterns:
        for m in pattern.finditer(html_text):
            link = m.groupdict().get("link") or ""
            if link:
                link = urljoin(base_url, link)
            else:
                href = re.search(r'href="([^"]+)"', m.group(0))
                link = urljoin(base_url, href.group(1)) if href else ""
            if not link or link in seen:
                continue
            title = clean_text(m.group("title"))
            if not title:
                continue
            when = parse_hhmm(m.group("time"), day=today)
            if when is None and m.groupdict().get("img"):
                when = parse_compact_date(m.group("img"))
            if when is None:
                when = dt.datetime.combine(today, dt.time.min, tzinfo=BEIJING)
            seen.add(link)
            items.append({"title": title, "link": link, "when": when})
    return items


def parse_jiemian(html_text: str, base_url: str) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    pattern = re.compile(
        r'<li class="card-list">.*?<a href="(?P<link>[^"]+)"[^>]*>.*?'
        r'<h3 class="card-list__title">(?P<title>.*?)</h3>.*?'
        r'<img src="(?P<img>[^"]+)".*?'
        r'<span class="news-footer__date">\s*(?P<date>\d{2}/\d{2})\s*(?P<time>\d{2}:\d{2})\s*</span>',
        re.S,
    )
    for m in pattern.finditer(html_text):
        link = urljoin(base_url, m.group("link"))
        if link in seen:
            continue
        title = clean_text(m.group("title"))
        if not title:
            continue
        img_dt = parse_compact_date(m.group("img"))
        year = img_dt.year if img_dt else dt.datetime.now(BEIJING).year
        when = parse_md_time(f"{m.group('date')} {m.group('time')}", year=year) or img_dt
        seen.add(link)
        items.append({"title": title, "link": link, "when": when})
    return items


def parse_huanqiu(html_text: str, base_url: str) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    pattern = re.compile(
        r'<div class="item"><textarea class="item-aid">(?P<aid>[^<]+)</textarea>'
        r'<textarea class="item-addltype">(?P<type>[^<]+)</textarea>'
        r'<textarea class="item-cover">(?P<cover>[^<]+)</textarea>'
        r'<textarea class="item-title">(?P<title>[^<]+)</textarea>'
        r'<textarea class="item-cnf-host">(?P<host>[^<]+)</textarea>'
        r'<textarea class="item-time">(?P<ts>\d+)</textarea></div>',
        re.S,
    )
    for m in pattern.finditer(html_text):
        host = m.group("host").strip()
        aid = m.group("aid").strip()
        link = f"https://{host}/article/{aid}"
        if link in seen:
            continue
        title = clean_text(m.group("title"))
        if not title:
            continue
        when = parse_epoch_ms(m.group("ts"))
        seen.add(link)
        items.append({"title": title, "link": link, "when": when})
    return items


def norm_title(title: str) -> str:
    """归一化标题用于去重：小写、去标点、压空白。"""
    s = re.sub(r"[\W_]+", " ", title.lower(), flags=re.UNICODE)
    return s.strip()


def main() -> int:
    # Windows 控制台默认 GBK，会在打印 ✓/✅ 等字符时报 UnicodeEncodeError；改用 UTF-8。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass  # 老版本 Python 或已被重定向的流，忽略即可

    ap = argparse.ArgumentParser(description="本地 RSS / 公开列表页抓取 → 候选清单 markdown")
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

    for spec in iter_sources():
        try:
            if spec.kind == "rss":
                raw = fetch(spec.url)
                items = extract_items(raw)
            else:
                html_text = fetch_text(spec.url)
                parser = spec.parser or (lambda _html, _url: [])
                items = parser(html_text, spec.url)
        except (urllib.error.URLError, ET.ParseError, json.JSONDecodeError, Exception) as e:  # noqa: BLE001
            report.append(f"  ✗ {spec.name:<22} 失败：{type(e).__name__}: {e}")
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
            it["source"] = spec.name
            by_region.setdefault(spec.region, []).append(it)
            kept += 1
        total_kept += kept
        report.append(f"  ✓ {spec.name:<22} 取到 {len(items):>3} 条，保留 {kept:>3} 条")
        time.sleep(POLITE_DELAY)

    # ── 写候选清单 ──────────────────────────────────────────────────────────
    lines: list[str] = []
    lines.append(f"# 新闻候选清单（原始）· {today}")
    _dedup_note = "未去重" if args.no_dedup else "去重后"
    lines.append(f"> 本地 RSS / 公开列表页抓取，过去 {args.hours} 小时，{_dedup_note}共 {total_kept} 条。")
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
