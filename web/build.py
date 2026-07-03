#!/usr/bin/env python3
"""Pre-compile digests/*.md into a static site under site/.

The markdown files remain the single source of truth; this script only renders
them. Run locally with `pip install markdown` or via the GitHub Pages workflow.

Usage:
    python web/build.py                 # -> site/
    python web/build.py --out PATH      # custom output dir
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import subprocess
from pathlib import Path

try:
    import markdown  # type: ignore
except ImportError:  # pragma: no cover - guidance for local runs
    raise SystemExit(
        "Missing dependency 'markdown'. Install it with:  pip install markdown"
    )

ROOT = Path(__file__).resolve().parent.parent
DIGESTS = ROOT / "digests"
WEB = ROOT / "web"
TEMPLATES = WEB / "templates"
STATIC = WEB / "static"

DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


class Doc:
    """One rendered digest page."""

    def __init__(self, path: Path):
        self.path = path
        self.slug = path.stem  # e.g. 2026-07-03 or weekly-2026-06-30
        raw = path.read_text(encoding="utf-8")
        self.title = self._first_heading(raw) or self.slug
        self.date = self._parse_date(path.stem)
        self.is_weekly = path.stem.startswith("weekly-")
        self.is_full = path.stem.endswith("-full")
        self.md = raw

    @staticmethod
    def _first_heading(raw: str) -> str | None:
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
        return None

    @staticmethod
    def _parse_date(stem: str) -> dt.date | None:
        m = DATE_RE.search(stem)
        if not m:
            return None
        try:
            return dt.date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None

    @property
    def out_name(self) -> str:
        return f"{self.slug}.html"

    def label(self) -> str:
        """Sidebar label."""
        base = self.date.isoformat() if self.date else self.slug
        if self.is_full:
            return f"{base} · 全量 full"
        return base


def collect_docs() -> list[Doc]:
    docs: list[Doc] = []
    for p in sorted(DIGESTS.glob("*.md")):
        if p.stem.startswith("_raw-"):
            continue
        docs.append(Doc(p))
    return docs


def render_md(md_text: str) -> str:
    return markdown.markdown(
        md_text,
        extensions=["extra", "sane_lists", "toc", "nl2br"],
        output_format="html5",
    )


def build_sidebar(docs: list[Doc], active: Doc) -> str:
    """Two switchable panels — Daily and Weekly. The active doc's kind is shown."""
    dailies = [d for d in docs if not d.is_weekly and not d.is_full]
    fulls = {d.slug.replace("-full", ""): d for d in docs if d.is_full}
    weeklies = [d for d in docs if d.is_weekly]

    # newest first
    dailies.sort(key=lambda d: (d.date or dt.date.min), reverse=True)
    weeklies.sort(key=lambda d: (d.date or dt.date.min), reverse=True)

    def link(d: Doc, text: str | None = None) -> str:
        cls = ' class="active"' if d.slug == active.slug else ""
        return f'<a href="{d.out_name}"{cls}>{html.escape(text or d.label())}</a>'

    active_kind = "weekly" if active.is_weekly else "daily"

    def tab(kind: str, label: str, count: int) -> str:
        cls = "tab active" if kind == active_kind else "tab"
        return (
            f'<button class="{cls}" data-tab="{kind}">'
            f'{label} <span class="tab-count">{count}</span></button>'
        )

    parts: list[str] = ['<div class="nav-tabs">']
    parts.append(tab("daily", "每日 Daily", len(dailies)))
    parts.append(tab("weekly", "每周 Weekly", len(weeklies)))
    parts.append("</div>")

    # Daily panel
    show = "" if active_kind == "daily" else ' hidden'
    parts.append(f'<div class="nav-panel" data-panel="daily"{show}><ul>')
    for d in dailies:
        extra = ""
        full = fulls.get(d.slug)
        if full:
            extra = f' <span class="full-link">({link(full, "full")})</span>'
        parts.append(f"<li>{link(d)}{extra}</li>")
    parts.append("</ul></div>")

    # Weekly panel
    show = "" if active_kind == "weekly" else ' hidden'
    parts.append(f'<div class="nav-panel" data-panel="weekly"{show}><ul>')
    if weeklies:
        for d in weeklies:
            parts.append(f"<li>{link(d)}</li>")
    else:
        parts.append('<li class="nav-empty">暂无每周综述</li>')
    parts.append("</ul></div>")

    return "\n".join(parts)


def load_template(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


# --- top navigation ------------------------------------------------------

NAV_ITEMS = [
    ("home", "首页 Home", "home.html"),
    ("daily", "每日 Daily", None),      # -> newest daily, filled at build
    ("weekly", "每周 Weekly", None),    # -> newest weekly, filled at build
    ("changelog", "更新 Changelog", "changelog.html"),
    ("stats", "统计 Stats", "stats.html"),
    ("achievements", "成就 Achievements", "achievements.html"),
]


def build_topnav(active: str, daily_href: str, weekly_href: str) -> str:
    links = []
    for key, label, href in NAV_ITEMS:
        if key == "daily":
            href = daily_href
        elif key == "weekly":
            href = weekly_href
        if not href:
            continue
        cls = ' class="active"' if key == active else ""
        links.append(f'<a href="{href}"{cls}>{html.escape(label)}</a>')
    return "".join(links)


# --- objective production stats (no tokens needed) -----------------------

def digest_metrics(d: Doc) -> dict:
    """Count objective things build can actually see in a daily digest."""
    text = d.md
    # bullet items = lines starting with "- **"
    items = len(re.findall(r"^- \*\*", text, re.MULTILINE))
    links = len(re.findall(r"\]\(https?://", text))
    # candidate count often stated as "（NNN 条候选）"
    cand = None
    m = re.search(r"(\d+)\s*条候选", text)
    if m:
        cand = int(m[1])
    chars = len(re.sub(r"\s", "", text))
    return {"items": items, "links": links, "candidates": cand, "chars": chars}


def load_usage() -> dict[str, dict]:
    """Optional token usage keyed by date, from stats/usage.jsonl if present.

    Each line: {"date": "2026-07-03", "input_tokens": N, "output_tokens": N}
    Absent file -> empty; the stats page then shows production metrics only.
    """
    f = ROOT / "stats" / "usage.jsonl"
    out: dict[str, dict] = {}
    if not f.exists():
        return out
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "date" in rec:
            out[str(rec["date"])] = rec
    return out


# --- standalone pages ----------------------------------------------------

def build_home(docs: list[Doc]) -> str:
    dailies = sorted(
        [d for d in docs if not d.is_weekly and not d.is_full],
        key=lambda d: (d.date or dt.date.min), reverse=True,
    )
    weeklies = sorted(
        [d for d in docs if d.is_weekly],
        key=lambda d: (d.date or dt.date.min), reverse=True,
    )
    latest = dailies[0] if dailies else None
    total_items = sum(digest_metrics(d)["items"] for d in dailies)

    p = ['<h1>每日新闻摘要 · Daily News Digest</h1>']
    p.append(
        '<p class="lede">云端定时任务自动巡视全球主流报纸，覆盖'
        '<strong>政治·国际 / 经济·财经 / 科技 / 社会·民生 / 灾害·突发</strong>'
        '五大类，去重后生成中文原创摘要并附原文链接。每期另附 '
        '<strong>📚 概念观察</strong> 栏目，从新闻抽取宏观经济学 &amp; 社会学概念配现实案例。</p>'
    )

    info = streak_info(daily_dates(docs))

    # stat row
    p.append('<div class="stat-row">')
    p.append(f'<div class="stat"><b>{len(dailies)}</b><span>每日期数 Daily</span></div>')
    p.append(f'<div class="stat"><b>{info["current"]}</b><span>连续天数 Streak</span></div>')
    p.append(f'<div class="stat"><b>{len(weeklies)}</b><span>每周综述 Weekly</span></div>')
    p.append(f'<div class="stat"><b>{total_items}</b><span>累计条目 Items</span></div>')
    p.append("</div>")

    # highest badge earned
    earned = [b for b in BADGES if info["longest"] >= b[0]]
    if earned:
        thr, emoji, zh, en, _blurb = earned[-1]
        nxt = next((b for b in BADGES if b[0] > info["longest"]), None)
        tail = ""
        if nxt:
            tail = f'，再连续 {nxt[0] - info["longest"]} 天解锁 {nxt[1]} {nxt[2]}'
        p.append(
            f'<a class="badge-teaser" href="achievements.html">'
            f'<span class="bt-icon">{emoji}</span>'
            f'<span class="bt-text">当前成就 <strong>{html.escape(zh)} · {html.escape(en)}</strong>'
            f'（连续 {thr} 天{tail}）→</span></a>'
        )

    if latest:
        p.append('<h2>最新一期 Latest</h2>')
        p.append(
            f'<a class="card" href="{latest.out_name}">'
            f'<div class="card-date">{latest.date.isoformat() if latest.date else latest.slug}</div>'
            f'<div class="card-title">{html.escape(latest.title)}</div>'
            f'<div class="card-cta">阅读全文 →</div></a>'
        )

    if len(dailies) > 1:
        p.append('<h2>近期每日 Recent</h2><ul class="link-list">')
        for d in dailies[1:8]:
            date = d.date.isoformat() if d.date else d.slug
            p.append(f'<li><a href="{d.out_name}"><span class="ll-date">{date}</span> {html.escape(d.title)}</a></li>')
        p.append("</ul>")

    p.append(
        '<p class="muted">运行说明见 <a href="https://github.com/cxy0714/social_news">仓库</a> 的 '
        '<code>instruction.md</code>；各来源媒体的类型 / 立场 / 领域见 <code>sources.md</code>。</p>'
    )
    return "\n".join(p)


def build_changelog() -> str:
    """Render recent git history grouped by date. Degrades gracefully."""
    try:
        raw = subprocess.run(
            ["git", "log", "--no-merges", "--date=short",
             "--pretty=%ad%x1f%s", "-n", "200"],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        raw = ""

    p = ['<h1>更新日志 Changelog</h1>',
         '<p class="muted">自动从 git 提交历史生成，最近 200 条。</p>']
    if not raw.strip():
        p.append('<p class="muted">暂无提交记录（git 不可用或仓库为空）。</p>')
        return "\n".join(p)

    by_date: dict[str, list[str]] = {}
    order: list[str] = []
    for line in raw.splitlines():
        if "\x1f" not in line:
            continue
        date, subj = line.split("\x1f", 1)
        if date not in by_date:
            by_date[date] = []
            order.append(date)
        by_date[date].append(subj)

    for date in order:
        p.append(f'<div class="cl-day"><h3>{html.escape(date)}</h3><ul>')
        for subj in by_date[date]:
            p.append(f"<li>{html.escape(subj)}</li>")
        p.append("</ul></div>")
    return "\n".join(p)


def build_stats(docs: list[Doc]) -> str:
    dailies = sorted(
        [d for d in docs if not d.is_weekly and not d.is_full],
        key=lambda d: (d.date or dt.date.min), reverse=True,
    )
    usage = load_usage()
    has_tokens = bool(usage)

    p = ['<h1>统计 Stats</h1>']
    p.append(
        '<p class="muted">下列产量指标由构建脚本从 digest 直接统计，客观可复现。'
        + ("token 用量来自 <code>stats/usage.jsonl</code>（云端生成时记录）。"
           if has_tokens else
           "token 用量需 <code>stats/usage.jsonl</code>，当前未提供，故仅显示产量。")
        + "</p>"
    )

    # totals
    tot_items = sum(digest_metrics(d)["items"] for d in dailies)
    tot_links = sum(digest_metrics(d)["links"] for d in dailies)
    tot_chars = sum(digest_metrics(d)["chars"] for d in dailies)
    p.append('<div class="stat-row">')
    p.append(f'<div class="stat"><b>{len(dailies)}</b><span>覆盖天数 Days</span></div>')
    p.append(f'<div class="stat"><b>{tot_items}</b><span>条目 Items</span></div>')
    p.append(f'<div class="stat"><b>{tot_links}</b><span>来源链接 Links</span></div>')
    p.append(f'<div class="stat"><b>{tot_chars // 1000}k</b><span>产出字数 Chars</span></div>')
    p.append("</div>")

    # per-day table
    p.append('<h2>逐期明细 Per-issue</h2>')
    p.append('<div class="table-wrap"><table class="stats-table"><thead><tr>'
             '<th>日期 Date</th><th>候选 Cand.</th><th>条目 Items</th>'
             '<th>链接 Links</th><th>字数 Chars</th>')
    if has_tokens:
        p.append('<th>输入 In</th><th>输出 Out</th>')
    p.append("</tr></thead><tbody>")
    for d in dailies:
        m = digest_metrics(d)
        date = d.date.isoformat() if d.date else d.slug
        row = [
            f'<td><a href="{d.out_name}">{date}</a></td>',
            f'<td>{m["candidates"] if m["candidates"] is not None else "—"}</td>',
            f'<td>{m["items"]}</td>',
            f'<td>{m["links"]}</td>',
            f'<td>{m["chars"]:,}</td>',
        ]
        if has_tokens:
            u = usage.get(date, {})
            it = u.get("input_tokens")
            ot = u.get("output_tokens")
            row.append(f'<td>{it:,}</td>' if isinstance(it, int) else "<td>—</td>")
            row.append(f'<td>{ot:,}</td>' if isinstance(ot, int) else "<td>—</td>")
        p.append("<tr>" + "".join(row) + "</tr>")
    p.append("</tbody></table></div>")
    return "\n".join(p)


# --- achievements --------------------------------------------------------

# (threshold_days, emoji, name_zh, name_en, blurb)
BADGES = [
    (1,   "🌱", "起步",   "First Step",  "发布第一期摘要"),
    (3,   "🔥", "三连",   "Streak 3",    "连续 3 天不间断"),
    (7,   "⭐", "一周",   "One Week",    "连续 7 天，一周不断更"),
    (14,  "🌟", "两周",   "Two Weeks",   "连续 14 天，习惯初成"),
    (30,  "🏅", "月度",   "One Month",   "连续 30 天，满月坚持"),
    (50,  "💎", "半百",   "Fifty",       "连续 50 天，稳如磐石"),
    (100, "👑", "百日",   "Century",     "连续 100 天，百日筑基"),
    (200, "🚀", "二百",   "Two Hundred", "连续 200 天，一往无前"),
    (365, "🏆", "周年",   "One Year",    "连续 365 天，全年无休"),
]


def daily_dates(docs: list[Doc]) -> list[dt.date]:
    ds = sorted({d.date for d in docs if not d.is_weekly and not d.is_full and d.date})
    return ds


def streak_info(dates: list[dt.date]) -> dict:
    """Longest and current consecutive-day streaks from a set of dates."""
    if not dates:
        return {"total": 0, "longest": 0, "current": 0, "first": None, "last": None}
    longest = cur = 1
    for prev, nxt in zip(dates, dates[1:]):
        if (nxt - prev).days == 1:
            cur += 1
        else:
            cur = 1
        longest = max(longest, cur)
    # current streak = run ending at the most recent date
    current = 1
    for prev, nxt in zip(reversed(dates[:-1]), reversed(dates)):
        if (nxt - prev).days == 1:
            current += 1
        else:
            break
    return {
        "total": len(dates), "longest": longest, "current": current,
        "first": dates[0], "last": dates[-1],
    }


def build_achievements(docs: list[Doc]) -> str:
    dates = daily_dates(docs)
    info = streak_info(dates)
    longest = info["longest"]

    p = ['<h1>成就 Achievements</h1>']
    p.append(
        '<p class="muted">徽章按<strong>连续发布天数</strong>解锁，依据 '
        '<code>digests/YYYY-MM-DD.md</code> 的日期自动计算（相邻日期算连续，断更则重新计数）。</p>'
    )

    # streak summary
    p.append('<div class="stat-row">')
    p.append(f'<div class="stat"><b>{info["longest"]}</b><span>最长连续 Longest</span></div>')
    p.append(f'<div class="stat"><b>{info["current"]}</b><span>当前连续 Current</span></div>')
    p.append(f'<div class="stat"><b>{info["total"]}</b><span>累计天数 Total</span></div>')
    p.append("</div>")

    unlocked = sum(1 for b in BADGES if longest >= b[0])
    p.append(
        f'<p class="muted">已解锁 <strong>{unlocked} / {len(BADGES)}</strong> 枚徽章'
        + (f'，最长连续 {longest} 天。' if longest else '。')
        + '</p>'
    )

    # badge grid
    p.append('<div class="badge-grid">')
    for thr, emoji, zh, en, blurb in BADGES:
        got = longest >= thr
        # progress toward the next locked badge
        cls = "badge" if got else "badge locked"
        state = "已解锁" if got else f"还差 {thr - longest} 天"
        p.append(
            f'<div class="{cls}">'
            f'<div class="badge-icon">{emoji}</div>'
            f'<div class="badge-name">{html.escape(zh)} · {html.escape(en)}</div>'
            f'<div class="badge-req">连续 {thr} 天</div>'
            f'<div class="badge-blurb">{html.escape(blurb)}</div>'
            f'<div class="badge-state">{state}</div>'
            f'</div>'
        )
    p.append("</div>")

    if not dates:
        p.append('<p class="muted">还没有每日摘要，发布第一期即可点亮 🌱。</p>')
    return "\n".join(p)


def build(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    docs = collect_docs()
    if not docs:
        raise SystemExit("No digests found under digests/*.md")

    page_tpl = load_template("page.html")
    standalone_tpl = load_template("standalone.html")

    # copy static assets
    assets_out = out_dir / "static"
    assets_out.mkdir(exist_ok=True)
    for asset in STATIC.glob("*"):
        (assets_out / asset.name).write_text(
            asset.read_text(encoding="utf-8"), encoding="utf-8"
        )

    dailies = sorted(
        [d for d in docs if not d.is_weekly and not d.is_full],
        key=lambda d: (d.date or dt.date.min), reverse=True,
    )
    weeklies = sorted(
        [d for d in docs if d.is_weekly],
        key=lambda d: (d.date or dt.date.min), reverse=True,
    )
    daily_href = (dailies[0] if dailies else docs[0]).out_name
    weekly_href = weeklies[0].out_name if weeklies else "home.html"

    # digest pages (with date sidebar)
    for d in docs:
        active = "weekly" if d.is_weekly else "daily"
        page = page_tpl.format(
            title=html.escape(d.title),
            slug=d.slug,
            topnav=build_topnav(active, daily_href, weekly_href),
            sidebar=build_sidebar(docs, d),
            content=render_md(d.md),
        )
        (out_dir / d.out_name).write_text(page, encoding="utf-8")

    # standalone pages
    standalone = [
        ("home", "首页 Home", "home.html", build_home(docs)),
        ("changelog", "更新日志 Changelog", "changelog.html", build_changelog()),
        ("stats", "统计 Stats", "stats.html", build_stats(docs)),
        ("achievements", "成就 Achievements", "achievements.html", build_achievements(docs)),
    ]
    for page_id, title, fname, content in standalone:
        page = standalone_tpl.format(
            title=html.escape(title),
            page_id=page_id,
            topnav=build_topnav(page_id, daily_href, weekly_href),
            content=content,
        )
        (out_dir / fname).write_text(page, encoding="utf-8")

    # index.html -> home page
    home_html = (out_dir / "home.html").read_text(encoding="utf-8")
    (out_dir / "index.html").write_text(home_html, encoding="utf-8")

    print(
        f"Built {len(docs)} digest pages + {len(standalone)} standalone -> {out_dir}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "site"), help="output directory")
    args = ap.parse_args()
    build(Path(args.out))


if __name__ == "__main__":
    main()
