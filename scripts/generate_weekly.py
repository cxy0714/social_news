#!/usr/bin/env python3
"""本地 API 版·每周综述生成（零第三方依赖）。

与每日 digest 并存的「周汇总」无人值守版：**不重新抓 RSS**，而是把当周已落地的
7 份日报 digests/YYYY-MM-DD.md 喂给 LLM，做跨日主线梳理 + 五类分区 + 中文原创综述，
渲染成 digests/weekly-YYYY-MM-DD.md（周日日期命名）→ 更新 README「每周综述」索引 →
可选 git commit/push（push 前先 pull --rebase）。

守 instruction.md §2 版权红线：输入是本仓库自己的原创日报，产出仍是原创中文综述 +
原文链接（链接直接沿用日报里的），不复制第三方原文。

用法：
    python3 scripts/generate_weekly.py                 # 本周（含今天所在周），不 commit
    python3 scripts/generate_weekly.py --date 2026-07-12   # 指定某周日/周内任一天
    python3 scripts/generate_weekly.py --commit        # 生成后 add/commit/push
    python3 scripts/generate_weekly.py --dry-run       # 只列当周日报文件，不调 LLM
    python3 scripts/generate_weekly.py --catch-up --commit   # 补已完结但缺的周综述

补缺模式（--catch-up）：扫过去 --lookback 天（默认 14）覆盖到的、已完结（周日≤今天）
且缺 weekly 文件的 ISO 周，逐周补齐（关机错过周日也能事后追上）。本周只有到周日当天
才算完结。用 ISO 周（周一→周日）；文件按周日日期命名。

仅标准库，Python 3.9+。
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

import generate_digest as gd
import llm_client

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

ROOT = gd.ROOT
DIGESTS = gd.DIGESTS
README = gd.README
BEIJING = gd.BEIJING
CATEGORIES = gd.CATEGORIES


def week_range(any_day: dt.date) -> tuple[dt.date, dt.date]:
    """返回 any_day 所在 ISO 周的 (周一, 周日)。"""
    monday = any_day - dt.timedelta(days=any_day.isoweekday() - 1)
    return monday, monday + dt.timedelta(days=6)


def collect_dailies(monday: dt.date, sunday: dt.date) -> tuple[list[dict], list[str]]:
    """读当周每天的 digests/YYYY-MM-DD.md 正文；返回 (有正文的天, 缺失的天)。"""
    present: list[dict] = []
    missing: list[str] = []
    d = monday
    while d <= sunday:
        ds = d.strftime("%Y-%m-%d")
        p = DIGESTS / f"{ds}.md"
        if p.exists():
            present.append({"date": ds, "text": p.read_text(encoding="utf-8")})
        else:
            missing.append(ds)
        d += dt.timedelta(days=1)
    return present, missing


SYSTEM_PROMPT = """\
你是一名严谨的新闻主编，为「学习宏观经济学与社会学的中文读者」编写一周新闻综述。
你会收到本周 7 天（周一至周日）的每日新闻摘要正文（均为本仓库自己的原创日报，含
中文小标题、摘要与原文链接）。任务：跨日梳理，产出一份**一周综述**。

1. 主线：挑出贯穿本周的 4-8 条核心主线（一句话看懂），每条给一个中文小标题
   （headline）+ 一段 40-80 字的中文综述（summary，串起本周进展、更新到最新数字），
   并从日报里选 1-3 个最相关的原文链接放进 reports。
2. 五类分区：政治·国际 / 经济·财经 / 科技 / 社会·民生 / 灾害·突发。每类保留本周
   最有价值的 4-8 条，合并同一事件的跨日报道，写中文小标题 + ≤60 字原创综述 +
   region 地区标签 + reports（原文链接，沿用日报里给的 URL）。
3. 全部为原创综述，用自己的话，绝不复制第三方原文段落。链接必须来自输入日报里出现过
   的 URL，不要编造。

严格输出**一个 JSON 对象**，结构：
{
  "mainlines": [
    {"headline": "中文小标题", "summary": "40-80字综述",
     "reports": [{"source": "BBC", "url": "https://..."}]}
  ],
  "categories": [
    {"name": "政治 · 国际", "items": [
      {"title": "中文小标题", "summary": "≤60字综述", "region": "中东",
       "reports": [{"source": "BBC", "url": "https://..."}]}
    ]}
  ]
}
name 必须用五个类目原文（政治 · 国际 / 经济 · 财经 / 科技 / 社会 · 民生 / 灾害 · 突发）。
reports 至少一条。只输出 JSON。"""


def build_user_payload(present: list[dict], monday: dt.date, sunday: dt.date) -> str:
    lines = [f"本周范围（北京时间）：{monday:%Y-%m-%d}（周一）→ {sunday:%Y-%m-%d}（周日）",
             f"以下是本周 {len(present)} 天的每日 digest 正文，请据此做一周综述：", ""]
    for d in present:
        lines.append(f"========== {d['date']} ==========")
        lines.append(d["text"])
        lines.append("")
    return "\n".join(lines)


def render_weekly(data: dict, monday: dt.date, sunday: dt.date,
                  present: list[dict], missing: list[str]) -> str:
    iso_year, iso_week, _ = monday.isocalendar()
    label = llm_client.model_label()
    out = [f"# 每周新闻综述 · {iso_year} 第 {iso_week} 周（{monday:%m-%d} → {sunday:%m-%d}）",
           f"> 生成时间：{sunday:%Y-%m-%d}（北京时间）｜数据来源：本周 {len(present)} 份日报"
           f"（digests/{monday:%Y-%m-%d} → {sunday:%Y-%m-%d}），由 {label} 做跨日主线梳理、"
           "五类分区与中文原创综述。", ""]
    out.append(f"## 一、本周主线（{len(data.get('mainlines', []))} 条，一句话看懂）")
    for i, m in enumerate(data.get("mainlines", []), 1):
        out.append(f"{i}. **{m.get('headline', '')}**：{m.get('summary', '')}")
        out.append(f"   {gd._fmt_reports(m.get('reports', []))}")
    out.append("")
    nums = ["二", "三", "四", "五", "六"]
    by_name = {c.get("name", ""): c.get("items", []) for c in data.get("categories", [])}
    for idx, cat in enumerate(CATEGORIES):
        out.append(f"## {nums[idx]}、{cat}")
        rows = by_name.get(cat, [])
        if not rows:
            out.append("- （本周本类无高价值条目）")
        for it in rows:
            region = it.get("region", "")
            tag = f" `{region}`" if region else ""
            out.append(f"- **{it.get('title', '（无标题）')}** — {it.get('summary', '')}{tag}")
            out.append(f"  {gd._fmt_reports(it.get('reports', []))}")
        out.append("")
    out += ["---",
            "_说明：本综述为原创跨日梳理并附原文链接，未复制第三方原文；链接沿用本周日报。_"]
    if missing:
        out.append(f"_本周缺失日报：{', '.join(missing)}（当天未生成 digest）。_")
    return "\n".join(out) + "\n"


def update_readme(iso_year: int, iso_week: int, monday: dt.date, sunday: dt.date) -> None:
    """把本周插入 README「每周综述」索引顶部，按周日日期去重，保留最近 12 条。"""
    if not README.exists():
        return
    text = README.read_text(encoding="utf-8")
    marker = "## 每周综述"
    if marker not in text:
        return
    head, _, tail = text.partition(marker)
    rest = tail.split("\n## ", 1)
    footer = "\n## " + rest[1] if len(rest) > 1 else ""
    body = rest[0]
    entry = (f"- [{iso_year} 第 {iso_week} 周（{monday:%m-%d} → {sunday:%m-%d}）]"
             f"(./digests/weekly-{sunday:%Y-%m-%d}.md)")
    existing = [ln for ln in body.splitlines()
                if ln.startswith("- [") and f"weekly-{sunday:%Y-%m-%d}.md" not in ln]
    merged = [entry] + existing
    merged = merged[:12]
    new_body = "\n\n" + "\n".join(merged) + "\n\n"
    README.write_text(head + marker + new_body + footer, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="本地 API 版每周综述生成")
    ap.add_argument("--date", default=None,
                    help="周内任一天 YYYY-MM-DD（默认今天北京时间）；据此定位所在 ISO 周")
    ap.add_argument("--commit", action="store_true", help="生成后 git add/commit/push（push 前先 pull --rebase）")
    ap.add_argument("--dry-run", action="store_true", help="只列当周日报文件，不调 LLM、不落盘")
    ap.add_argument("--provider", choices=["deepseek", "claude"], default=None,
                    help="覆盖 .env 的 LLM_PROVIDER（本次用哪个模型）")
    ap.add_argument("--out", default=None, help="覆盖输出路径（默认 digests/weekly-周日.md）")
    ap.add_argument("--catch-up", action="store_true",
                    help="补缺模式：过去 --lookback 天里已完结但缺 weekly 的周逐周补齐")
    ap.add_argument("--lookback", type=int, default=14,
                    help="补缺回溯天数（默认 14，约覆盖最近两周）")
    args = ap.parse_args()

    llm_client.load_dotenv()
    if args.provider:
        import os
        os.environ["LLM_PROVIDER"] = args.provider

    if args.catch_up:
        return run_catch_up(args)

    any_day = (dt.datetime.strptime(args.date, "%Y-%m-%d").date() if args.date
               else dt.datetime.now(BEIJING).date())
    monday, sunday = week_range(any_day)
    iso_year, iso_week, _ = monday.isocalendar()
    print(f"→ 目标周：{iso_year} 第 {iso_week} 周（{monday} → {sunday}）")

    present, missing = collect_dailies(monday, sunday)
    print(f"  找到日报 {len(present)} 份；缺失 {len(missing)} 天：{', '.join(missing) or '无'}")
    if args.dry_run:
        for d in present:
            print(f"  - {d['date']}.md（{len(d['text'])} 字）")
        print("(dry-run) 未调 LLM。")
        return 0
    if not produce_weekly(monday, sunday, out=args.out):
        return 1
    if args.commit:
        gd.git_commit_push(f"{sunday:%Y-%m-%d}", message=f"weekly: {iso_year}-W{iso_week:02d}")
    else:
        print("（未加 --commit，未提交 git）")
    return 0


def produce_weekly(monday: dt.date, sunday: dt.date, *, out: str | None = None,
                   update_index: bool = True) -> bool:
    """产出一周综述（调 LLM + 落盘 + 可选更新 README），不做 git。返回是否写成功。"""
    iso_year, iso_week, _ = monday.isocalendar()
    present, missing = collect_dailies(monday, sunday)
    if not present:
        print(f"  ⚠ {iso_year}-W{iso_week:02d} 无任何日报，跳过。")
        return False
    print(f"→ 调用 LLM（{llm_client.model_label()}）做 {iso_year}-W{iso_week:02d} 综述"
          f"（{len(present)} 份日报）…")
    try:
        data = llm_client.chat_json(SYSTEM_PROMPT, build_user_payload(present, monday, sunday))
    except llm_client.LLMError as e:
        print(f"✗ {e}")
        return False
    md = render_weekly(data, monday, sunday, present, missing)
    out_path = Path(out) if out else DIGESTS / f"weekly-{sunday:%Y-%m-%d}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    print(f"✅ 已写入 {out_path}")
    if update_index and not out:
        update_readme(iso_year, iso_week, monday, sunday)
        print("✅ 已更新 README「每周综述」索引")
    return True


def missing_weeks(lookback: int) -> list[tuple[dt.date, dt.date]]:
    """过去 lookback 天覆盖到的、已完结（周日≤今天）且缺 weekly 文件的周，由旧到新。

    本周只有到周日当天才算「已完结」；缺 weekly 且当周至少有一份日报才补。"""
    today = dt.datetime.now(BEIJING).date()
    seen: set[dt.date] = set()
    out: list[tuple[dt.date, dt.date]] = []
    for back in range(lookback, -1, -1):
        mon, sun = week_range(today - dt.timedelta(days=back))
        if sun in seen or sun > today:
            continue
        seen.add(sun)
        if (DIGESTS / f"weekly-{sun:%Y-%m-%d}.md").exists():
            continue
        present, _ = collect_dailies(mon, sun)
        if present:
            out.append((mon, sun))
    return out


def run_catch_up(args) -> int:
    """补缺：过去 --lookback 天里已完结但缺 weekly 的周，逐周补齐。"""
    todo = missing_weeks(args.lookback)
    if not todo:
        print(f"✓ 过去 {args.lookback} 天内各周综述齐全，无需补缺。")
        return 0
    labels = [f"{m.isocalendar()[0]}-W{m.isocalendar()[1]:02d}" for m, _ in todo]
    print(f"→ 缺 {len(todo)} 周综述：{', '.join(labels)}")
    wrote: list[tuple[dt.date, dt.date]] = []
    for mon, sun in todo:
        if produce_weekly(mon, sun):
            wrote.append((mon, sun))
    if not wrote:
        print("⚠ 补缺未产出任何周综述。")
        return 0
    if args.commit:
        first, last = wrote[0][0], wrote[-1][0]
        fy, fw, _ = first.isocalendar()
        ly, lw, _ = last.isocalendar()
        msg = (f"weekly: catch-up {fy}-W{fw:02d}..{ly}-W{lw:02d}"
               if len(wrote) > 1 else f"weekly: {fy}-W{fw:02d}")
        gd.git_commit_push(f"{wrote[-1][1]:%Y-%m-%d}", message=msg)
    else:
        print("（未加 --commit，未提交 git）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
