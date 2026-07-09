#!/usr/bin/env python3
"""Compile digests/*.md into ONE self-contained index.html under site/.

The markdown files remain the single source of truth; this script only renders
them. The output is a single file with CSS/JS inlined and every digest embedded
as a hidden <section> switched client-side via the URL hash — so it works from a
plain file:// double-click, no server, offline. Bookmark the local file once and
each rebuild just overwrites it in place.

Usage:
    python web/build.py                 # -> site/index.html
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
FUTURE = ROOT / "future-tech"
WEB = ROOT / "web"
STATIC = WEB / "static"
SOURCES = ROOT / "sources.md"

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
    def view_id(self) -> str:
        return self.slug

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


class Report:
    """One future-tech deep-dive report under future-tech/."""

    def __init__(self, path: Path):
        self.path = path
        self.slug = "ft-" + path.stem  # view id, namespaced to avoid clashes
        raw = path.read_text(encoding="utf-8")
        self.title = Doc._first_heading(raw) or path.stem
        self.date = Doc._parse_date(path.stem)
        self.md = raw

    @property
    def view_id(self) -> str:
        return self.slug

    def summary(self) -> str:
        """First non-empty prose line after the front-matter blockquotes."""
        for line in self.md.splitlines():
            s = line.strip()
            if not s or s.startswith("#") or s.startswith(">") or s.startswith("-"):
                continue
            if s.startswith("**") or s.startswith("_"):
                continue
            return re.sub(r"[*`]", "", s)[:90]
        return ""


def collect_reports() -> list[Report]:
    reports: list[Report] = []
    if FUTURE.exists():
        for p in sorted(FUTURE.glob("*.md")):
            if p.stem.upper() == "README":
                continue
            reports.append(Report(p))
    reports.sort(key=lambda r: (r.date or dt.date.min), reverse=True)
    return reports


# Cross-digest links in the markdown look like [text](./2026-07-01-full.md).
# In the single-file site every digest is an in-page view, so rewrite those to
# the matching #hash. The digest markdown stays untouched — this is render-only.
_MD_LINK_RE = re.compile(r'href="\.?/?([^"/]+)\.md"')


def render_md(md_text: str) -> str:
    out = markdown.markdown(
        md_text,
        extensions=["extra", "sane_lists", "toc", "nl2br"],
        output_format="html5",
    )
    return _MD_LINK_RE.sub(r'href="#\1"', out)


# --- sidebar (date rail) -------------------------------------------------

def build_sidebar(docs: list[Doc]) -> str:
    """Two switchable panels — Daily and Weekly. Links are in-page hashes."""
    dailies = [d for d in docs if not d.is_weekly and not d.is_full]
    fulls = {d.slug.replace("-full", ""): d for d in docs if d.is_full}
    weeklies = [d for d in docs if d.is_weekly]

    dailies.sort(key=lambda d: (d.date or dt.date.min), reverse=True)
    weeklies.sort(key=lambda d: (d.date or dt.date.min), reverse=True)

    def link(d: Doc, text: str | None = None) -> str:
        return f'<a href="#{d.view_id}">{html.escape(text or d.label())}</a>'

    def tab(kind: str, label: str, count: int, active: bool) -> str:
        cls = "tab active" if active else "tab"
        return (
            f'<button class="{cls}" data-tab="{kind}">'
            f'{label} <span class="tab-count">{count}</span></button>'
        )

    parts: list[str] = ['<div class="nav-tabs">']
    parts.append(tab("daily", "每日 Daily", len(dailies), True))
    parts.append(tab("weekly", "每周 Weekly", len(weeklies), False))
    parts.append("</div>")

    # Daily panel
    parts.append('<div class="nav-panel" data-panel="daily"><ul>')
    for d in dailies:
        extra = ""
        full = fulls.get(d.slug)
        if full:
            extra = f' <span class="full-link">({link(full, "full")})</span>'
        parts.append(f"<li>{link(d)}{extra}</li>")
    parts.append("</ul></div>")

    # Weekly panel (hidden by default; JS reveals when a weekly is shown)
    parts.append('<div class="nav-panel" data-panel="weekly" hidden><ul>')
    if weeklies:
        for d in weeklies:
            parts.append(f"<li>{link(d)}</li>")
    else:
        parts.append('<li class="nav-empty">暂无每周综述</li>')
    parts.append("</ul></div>")

    return "\n".join(parts)


# --- top navigation ------------------------------------------------------

def build_topnav(daily_href: str, weekly_href: str) -> str:
    items = [
        ("home", "首页 Home", "#home"),
        ("daily", "每日 Daily", daily_href),
        ("weekly", "每周 Weekly", weekly_href),
        ("future", "未来技术 Future", "#future"),
        ("sources", "来源 Sources", "#sources"),
        ("changelog", "更新 Changelog", "#changelog"),
        ("stats", "统计 Stats", "#stats"),
    ]
    links = []
    for key, label, href in items:
        links.append(f'<a href="{href}" data-nav="{key}">{html.escape(label)}</a>')
    return "".join(links)


# --- objective production stats (no tokens needed) -----------------------

def digest_metrics(d: Doc) -> dict:
    """Count objective things build can actually see in a daily digest."""
    text = d.md
    items = len(re.findall(r"^- \*\*", text, re.MULTILINE))
    links = len(re.findall(r"\]\(https?://", text))
    cand = None
    m = re.search(r"(\d+)\s*条候选", text)
    if m:
        cand = int(m[1])
    chars = len(re.sub(r"\s", "", text))
    return {"items": items, "links": links, "candidates": cand, "chars": chars}


def load_usage() -> dict[str, dict]:
    """Optional token usage keyed by date, from stats/usage.jsonl if present."""
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


# --- standalone views ----------------------------------------------------

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

    p.append('<div class="stat-row">')
    p.append(f'<div class="stat"><b>{len(dailies)}</b><span>每日期数 Daily</span></div>')
    p.append(f'<div class="stat"><b>{len(weeklies)}</b><span>每周综述 Weekly</span></div>')
    p.append(f'<div class="stat"><b>{total_items}</b><span>累计条目 Items</span></div>')
    p.append("</div>")

    if latest:
        p.append('<h2>最新一期 Latest</h2>')
        p.append(
            f'<a class="card" href="#{latest.view_id}">'
            f'<div class="card-date">{latest.date.isoformat() if latest.date else latest.slug}</div>'
            f'<div class="card-title">{html.escape(latest.title)}</div>'
            f'<div class="card-cta">阅读全文 →</div></a>'
        )

    if len(dailies) > 1:
        p.append('<h2>近期每日 Recent</h2><ul class="link-list">')
        for d in dailies[1:8]:
            date = d.date.isoformat() if d.date else d.slug
            p.append(f'<li><a href="#{d.view_id}"><span class="ll-date">{date}</span> {html.escape(d.title)}</a></li>')
        p.append("</ul>")

    p.append(
        '<p class="muted">运行说明见 <a href="https://github.com/cxy0714/social_news" target="_blank" rel="noopener">仓库</a> 的 '
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


def build_sources() -> str:
    """Render sources.md as a standalone page."""
    if not SOURCES.exists():
        return '<h1>来源媒体介绍 · Sources Guide</h1><p class="muted">sources.md 文件未找到。</p>'
    raw = SOURCES.read_text(encoding="utf-8")
    return render_md(raw)


def build_future(reports: list[Report]) -> str:
    """Landing page for the future-tech layer: watchlist widget + report cards."""
    p = ['<h1>未来技术 · Future Tech</h1>']
    p.append(
        '<p class="lede">从每日新闻里<strong>收藏</strong>一条值得深挖的（多为科技/'
        '未来技术类），以它为起点写一篇<strong>结构化深度调研报告</strong>。收藏清单存在'
        '你的私密 GitHub Gist，报告作为 markdown 归档进仓库。</p>'
    )

    # Watchlist widget — JS fills it from the configured Gist at runtime.
    p.append('<div class="wl">')
    p.append('<div class="wl-head">'
             '<h2>📌 待调研 Watchlist</h2>'
             '<div class="wl-actions">'
             '<button id="wl-refresh" class="btn-sm" type="button">刷新</button>'
             '<button id="wl-settings" class="btn-sm" type="button">⚙ 设置 Gist</button>'
             '</div></div>')
    p.append('<div id="wl-list" class="wl-list">'
             '<p class="muted" id="wl-empty">未配置 Gist。点“⚙ 设置 Gist”填入 Gist ID 与 '
             'token，即可在任意新闻条目旁用 ☆ 收藏，这里会列出待调研项。</p></div>')
    p.append('</div>')

    # Report cards
    p.append('<h2>调研报告 Reports</h2>')
    if reports:
        p.append('<div class="ft-cards">')
        for r in reports:
            date = r.date.isoformat() if r.date else r.slug
            summ = html.escape(r.summary())
            p.append(
                f'<a class="ft-card" href="#{r.view_id}">'
                f'<div class="card-date">{date}</div>'
                f'<div class="card-title">{html.escape(r.title)}</div>'
                f'<div class="ft-card-sum">{summ}</div>'
                f'<div class="card-cta">阅读报告 →</div></a>'
            )
        p.append('</div>')
    else:
        p.append('<p class="muted">暂无报告。收藏一条新闻后对我说“从这条写一篇未来技术调研”。</p>')

    p.append(
        '<p class="muted">这一层的说明见仓库 <code>future-tech/README.md</code>；'
        '收藏机制与版权红线同 <code>instruction.md</code>。</p>'
    )
    return "\n".join(p)


def report_section(r: Report) -> str:
    return (
        f'<section class="view-digest" data-view="{r.view_id}" data-kind="future" '
        f'data-nav="future" data-title="{html.escape(r.title)}" hidden>\n'
        f'<article class="prose">\n{render_md(r.md)}\n</article>\n'
        f'<footer class="page-foot">\n'
        f'本报告为原创综述并附来源链接，遵守版权红线（不复制原文、不绕过付费墙）。'
        f'分析性观点基于公开资料，非投资建议。\n</footer>\n</section>'
    )


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

    tot_items = sum(digest_metrics(d)["items"] for d in dailies)
    tot_links = sum(digest_metrics(d)["links"] for d in dailies)
    tot_chars = sum(digest_metrics(d)["chars"] for d in dailies)
    p.append('<div class="stat-row">')
    p.append(f'<div class="stat"><b>{len(dailies)}</b><span>覆盖天数 Days</span></div>')
    p.append(f'<div class="stat"><b>{tot_items}</b><span>条目 Items</span></div>')
    p.append(f'<div class="stat"><b>{tot_links}</b><span>来源链接 Links</span></div>')
    p.append(f'<div class="stat"><b>{tot_chars // 1000}k</b><span>产出字数 Chars</span></div>')
    p.append("</div>")

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
            f'<td><a href="#{d.view_id}">{date}</a></td>',
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


# --- page assembly -------------------------------------------------------

HEAD_TMPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>每日新闻摘要 · Daily News Digest</title>
<meta name="description" content="每日新闻摘要 Daily News Digest — 政治·国际 / 经济·财经 / 科技 / 社会·民生 / 灾害·突发。原创中文摘要 + 原文链接。">
<style>
{css}
</style>
</head>
<body>
<script>
// apply theme before paint to avoid flash
(function(){{try{{var t=localStorage.getItem('theme');if(t)document.documentElement.dataset.theme=t;}}catch(e){{}}}})();
</script>
<header class="topbar">
  <button id="nav-toggle" class="icon-btn" aria-label="Toggle navigation">☰</button>
  <a class="brand" href="#home">
    <span class="brand-zh">每日新闻摘要</span>
    <span class="brand-en">Daily News Digest</span>
  </a>
  <nav class="topnav">{topnav}</nav>
  <button id="theme-toggle" class="icon-btn" aria-label="Toggle theme">◐</button>
</header>
<div class="layout">
  <aside id="sidebar" class="sidebar">
    <nav>
{sidebar}
    </nav>
    <div class="sidebar-foot">
      <a href="https://github.com/cxy0714/social_news" target="_blank" rel="noopener">GitHub</a>
    </div>
  </aside>
  <main class="reader">
"""

FOOT_TMPL = """  </main>
</div>
<div id="scrim" class="scrim"></div>
<div id="gist-modal" class="modal" hidden>
  <div class="modal-card">
    <h3>收藏设置 · GitHub Gist</h3>
    <p class="muted">收藏清单存在你的一个私密 Gist。ID 与 token 仅存于本浏览器
    (localStorage)，<strong>不会进仓库</strong>。token 需 <code>gist</code> 权限。</p>
    <label>Gist ID<input id="gist-id" type="text" placeholder="如 a1b2c3d4..." autocomplete="off"></label>
    <label>Token (仅 gist 权限)<input id="gist-token" type="password" placeholder="ghp_... / github_pat_..." autocomplete="off"></label>
    <p class="muted modal-hint">还没有？到 <a href="https://gist.github.com" target="_blank" rel="noopener">gist.github.com</a>
    新建一个私密 Gist（文件名 <code>watchlist.json</code>，内容 <code>[]</code>），URL 末段即 ID；
    token 在 <a href="https://github.com/settings/tokens" target="_blank" rel="noopener">Settings → Tokens</a> 生成。</p>
    <div class="modal-actions">
      <button id="gist-clear" class="btn-sm" type="button">清除</button>
      <span class="modal-spacer"></span>
      <button id="gist-cancel" class="btn-sm" type="button">取消</button>
      <button id="gist-save" class="btn-sm btn-primary" type="button">保存</button>
    </div>
    <p id="gist-msg" class="modal-msg" hidden></p>
  </div>
</div>
<script>
{js}
</script>
</body>
</html>
"""


def digest_section(d: Doc, is_default: bool) -> str:
    default_attr = " data-default" if is_default else ""
    kind = "weekly" if d.is_weekly else "daily"
    return (
        f'<section class="view-digest" data-view="{d.view_id}" data-kind="{kind}" '
        f'data-title="{html.escape(d.title)}"{default_attr} hidden>\n'
        f'<article class="prose">\n{render_md(d.md)}\n</article>\n'
        f'<footer class="page-foot">\n'
        f'所有摘要均为原创概述并附原文链接，遵守版权红线（不复制原文、不绕过付费墙）。'
        f'来源如实标注，不做立场加工。\n</footer>\n</section>'
    )


def standalone_section(view_id: str, title: str, body: str, is_default: bool = False) -> str:
    default_attr = " data-default" if is_default else ""
    return (
        f'<section class="view-standalone" data-view="{view_id}" data-kind="standalone" '
        f'data-nav="{view_id}" data-title="{html.escape(title)}"{default_attr} hidden>\n'
        f'<div class="page-inner">\n{body}\n</div>\n</section>'
    )


def build(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    docs = collect_docs()
    if not docs:
        raise SystemExit("No digests found under digests/*.md")
    reports = collect_reports()

    css = (STATIC / "style.css").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")

    dailies = sorted(
        [d for d in docs if not d.is_weekly and not d.is_full],
        key=lambda d: (d.date or dt.date.min), reverse=True,
    )
    weeklies = sorted(
        [d for d in docs if d.is_weekly],
        key=lambda d: (d.date or dt.date.min), reverse=True,
    )
    daily_href = f"#{(dailies[0] if dailies else docs[0]).view_id}"
    weekly_href = f"#{weeklies[0].view_id}" if weeklies else "#home"

    parts: list[str] = [
        HEAD_TMPL.format(
            css=css,
            topnav=build_topnav(daily_href, weekly_href),
            sidebar=build_sidebar(docs),
        )
    ]

    # home is the default landing view when there is no hash
    parts.append(standalone_section("home", "首页 Home", build_home(docs), is_default=True))
    for d in docs:
        parts.append(digest_section(d, is_default=False))
    parts.append(standalone_section("future", "未来技术 Future Tech", build_future(reports)))
    for r in reports:
        parts.append(report_section(r))
    parts.append(standalone_section("sources", "来源媒体介绍 Sources Guide", build_sources()))
    parts.append(standalone_section("changelog", "更新日志 Changelog", build_changelog()))
    parts.append(standalone_section("stats", "统计 Stats", build_stats(docs)))

    parts.append(FOOT_TMPL.format(js=js))
    doc_html = "\n".join(parts)

    (out_dir / "index.html").write_text(doc_html, encoding="utf-8")
    print(
        f"Built single-file site: {len(docs)} digests + {len(reports)} reports "
        f"+ 5 pages -> {out_dir / 'index.html'}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "site"), help="output directory")
    args = ap.parse_args()
    build(Path(args.out))


if __name__ == "__main__":
    main()
