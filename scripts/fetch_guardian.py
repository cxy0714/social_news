#!/usr/bin/env python3
"""
The Guardian 官方 API 抓取脚本（可按日期范围真·回溯，零第三方依赖）。

为什么需要它：RSS 只缓存各源最新数十条，抓不到一周前的旧闻。
The Guardian Open Platform 提供按日期检索**全 archive** 的能力，因此能拿到「真正的一周」。

设计原则（守住版权与礼貌使用）：
- 只取 标题/链接/发布时间/栏目，**不抓正文全文**（API 默认也只返回元数据）。
- 分页拉取、页间限速；失败自动重试一次再跳过。
- 免费 key、明确 ToS 内使用。

前置：在 https://open-platform.theguardian.com/access/ 免费申请 key（即时发放），然后：
    Windows PowerShell:  $env:GUARDIAN_API_KEY = "你的key"
    Bash:                export GUARDIAN_API_KEY="你的key"

用法：
    python3 scripts/fetch_guardian.py                 # 默认过去 7 天
    python3 scripts/fetch_guardian.py --days 7
    python3 scripts/fetch_guardian.py --from 2026-06-23 --to 2026-06-30
    python3 scripts/fetch_guardian.py --out digests/_raw-guardian-2026-06-30.md

仅标准库，Python 3.9+ 即可运行。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Windows 控制台默认 GBK，打印 ✓/✗ 等字符会崩；强制 UTF-8 输出（含 stderr）。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

API = "https://content.guardianapis.com/search"
UA = "SocialNewsDigest/1.0 (+https://github.com/) Python-urllib"
TIMEOUT = 20
POLITE_DELAY = 0.3       # 页间间隔（秒）
PAGE_SIZE = 50           # API 单页上限 50
MAX_PAGES = 40           # 安全上限，防失控分页

# 只保留这些「硬新闻」栏目，过滤体育/娱乐/生活方式花边（按需增删）。
KEEP_SECTIONS = {
    "World news", "US news", "UK news", "Australia news", "Politics",
    "Business", "Economics", "Technology", "Environment", "Science",
    "Society", "Global development", "Money", "Law",
}


def fetch_page(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_page_retry(params: dict) -> dict:
    try:
        return fetch_page(params)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        time.sleep(1.0)
        return fetch_page(params)  # 重试一次；再失败则向上抛出


def main() -> int:
    ap = argparse.ArgumentParser(description="The Guardian API 按日期范围抓取 → 候选清单 markdown")
    ap.add_argument("--days", type=int, default=7, help="过去 N 天（默认 7）；与 --from/--to 互斥")
    ap.add_argument("--from", dest="from_date", help="起始日期 YYYY-MM-DD（含）")
    ap.add_argument("--to", dest="to_date", help="结束日期 YYYY-MM-DD（含）")
    today = dt.date.today()
    ap.add_argument("--out", default=f"digests/_raw-guardian-{today.isoformat()}.md", help="输出文件路径")
    args = ap.parse_args()

    key = os.environ.get("GUARDIAN_API_KEY")
    if not key:
        print("✗ 缺少 GUARDIAN_API_KEY 环境变量。", file=sys.stderr)
        print("  免费申请：https://open-platform.theguardian.com/access/", file=sys.stderr)
        print('  设置：PowerShell `$env:GUARDIAN_API_KEY="你的key"`；Bash `export GUARDIAN_API_KEY=你的key`', file=sys.stderr)
        return 2

    if args.from_date and args.to_date:
        from_date, to_date = args.from_date, args.to_date
    else:
        to_date = today.isoformat()
        from_date = (today - dt.timedelta(days=args.days - 1)).isoformat()

    base = {
        "from-date": from_date,
        "to-date": to_date,
        "order-by": "newest",
        "page-size": PAGE_SIZE,
        "api-key": key,
    }

    items: list[dict] = []
    page = 1
    total_pages = 1
    while page <= total_pages and page <= MAX_PAGES:
        params = dict(base, page=page)
        try:
            data = fetch_page_retry(params)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:  # noqa: BLE001
            print(f"  ✗ 第 {page} 页失败：{type(e).__name__}: {e}", file=sys.stderr)
            break
        resp = data.get("response", {})
        if resp.get("status") != "ok":
            print(f"  ✗ API 返回非 ok：{resp.get('status')} / {resp.get('message')}", file=sys.stderr)
            break
        total_pages = resp.get("pages", 1)
        for r in resp.get("results", []):
            items.append({
                "title": r.get("webTitle", "").strip(),
                "link": r.get("webUrl", "").strip(),
                "when": r.get("webPublicationDate", ""),   # ISO8601
                "section": r.get("sectionName", "").strip(),
            })
        print(f"  ✓ 第 {page}/{total_pages} 页，累计 {len(items)} 条")
        page += 1
        time.sleep(POLITE_DELAY)

    # 过滤栏目 + 去重（按链接）
    seen: set[str] = set()
    kept: list[dict] = []
    for it in items:
        if KEEP_SECTIONS and it["section"] not in KEEP_SECTIONS:
            continue
        if not it["link"] or it["link"] in seen:
            continue
        seen.add(it["link"])
        kept.append(it)

    # 按栏目分组输出
    by_section: dict[str, list[dict]] = {}
    for it in kept:
        by_section.setdefault(it["section"], []).append(it)

    lines: list[str] = []
    lines.append(f"# Guardian 候选清单（{from_date} → {to_date}）")
    lines.append(f"> The Guardian API 按日期回溯，过滤硬新闻栏目、去重后共 {len(kept)} 条。")
    lines.append("> 下一步：在 Claude Code 里让它读本文件做分类+中文摘要，并可与 RSS 候选合并。")
    lines.append("")
    for section in sorted(by_section, key=lambda s: -len(by_section[s])):
        rows = by_section[section]
        lines.append(f"## {section}（{len(rows)}）")
        for r in rows:
            ts = r["when"].replace("T", " ").replace("Z", " UTC") if r["when"] else "时间未知"
            lines.append(f"- [{r['title']}]({r['link']}) — {ts}")
        lines.append("")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n✅ 区间 {from_date} → {to_date}，过滤去重后保留 {len(kept)} 条，已写入：{args.out}")
    print(f"   下一步：在 Claude Code 里说「读 {args.out} 做分类和中文摘要」")
    return 0


if __name__ == "__main__":
    sys.exit(main())
