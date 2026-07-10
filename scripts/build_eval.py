#!/usr/bin/env python3
"""模型测评：同一天的 digest，DeepSeek vs Claude 并排对比，写入 evals/YYYY-MM-DD.md。

设计（用户选择：复用现有 DeepSeek 版）：
- DeepSeek 方：直接复用已生成的 `digests/YYYY-MM-DD.md` 正文（不重跑，省一次调用）。
- Claude   方：用 generate_digest 的流水线现抓 RSS+正文、调 Claude 生成正文。
  注意：候选来自当次 RSS，可能与 DeepSeek 那次不完全一致（可接受的对比误差）。

产出 `evals/YYYY-MM-DD.md` 是入库 markdown（唯一事实来源），网页层 web/build.py
渲染成「模型测评」tab。守版权红线：正文只喂 LLM，产出仍是原创摘要+链接。

用法：
    python3 scripts/build_eval.py                    # 今天，对比 deepseek vs claude
    python3 scripts/build_eval.py --date 2026-07-10
    python3 scripts/build_eval.py --commit           # 生成后 add/commit/push
仅标准库，Python 3.9+。
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
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
EVALS = ROOT / "evals"
BEIJING = gd.BEIJING


def extract_digest_body(md: str) -> str:
    """从一份完整 digest markdown 里抠出正文（首个 `## ` 到尾注 `\\n---\\n_说明` 前）。"""
    start = md.find("\n## ")
    if start < 0:
        return md.strip()
    body = md[start + 1:]
    # 砍掉结尾的「_说明…_ / _本日未覆盖…_」尾注段（最后一个 --- 之后若全是斜体行）。
    m = re.search(r"\n---\n_说明", body)
    if m:
        body = body[: m.start()]
    return body.strip()


def demote_headings(body: str, levels: int = 1) -> str:
    """把 markdown 标题整体降 N 级（## → ###），让它挂在 provider 的 ## 之下。"""
    bump = "#" * levels
    return re.sub(r"^(#{1,5}) ", lambda m: bump + m.group(1) + " ", body, flags=re.MULTILINE)


def deepseek_side(date_str: str) -> tuple[str, str]:
    """复用现有 digests/YYYY-MM-DD.md 作为 DeepSeek 方，返回 (标签, 正文)。"""
    path = gd.DIGESTS / f"{date_str}.md"
    if not path.exists():
        raise SystemExit(f"找不到 {path.relative_to(ROOT)}（先跑 generate_digest.py 生成 DeepSeek 版）")
    md = path.read_text(encoding="utf-8")
    m = re.search(r"由 (\S+?) 分类", md)
    label = m.group(1) if m else "deepseek:deepseek-chat"
    return label, extract_digest_body(md)


def claude_side(date_str: str, hours: int, max_items: int,
                body_chars: int) -> tuple[str, str, int, list[str]]:
    """现抓候选 + 正文，调 Claude 生成正文。返回 (标签, 正文, 候选数, 不可达源)。

    注意：Claude 走 api.anthropic.com，网关对单请求有 ~100s 上限；候选×正文过大时
    会 524 超时。默认用比 daily 更保守的规模（候选/正文都更小），既避超时也省 token。"""
    os.environ["LLM_PROVIDER"] = "claude"
    print(f"→ [Claude] 抓 RSS 候选（过去 {hours}h）…")
    items, unreachable = gd.collect_candidates(hours, max_items)
    print(f"  候选 {len(items)} 条；不可达 {len(unreachable)} 个")
    if body_chars > 0:
        print(f"→ [Claude] 抓公开正文摘录（每条 ≤{body_chars} 字，仅喂 LLM）…")
        for it in items:
            it["body"] = gd.fetch_body(it["link"], limit=body_chars)
    label = llm_client.model_label()
    print(f"→ [Claude] 调用 {label} 分类去重+摘要…")
    data = llm_client.chat_json(gd.SYSTEM_PROMPT, gd.build_user_payload(items, date_str))
    return label, gd.render_body(data), len(items), unreachable


def render_eval(date_str: str, ds_label: str, ds_body: str,
                cl_label: str, cl_body: str, cl_kept: int,
                cl_unreachable: list[str]) -> str:
    out = [f"# 模型测评 · {date_str}",
           f"> 生成时间：{date_str}（北京时间）",
           "> 同一天的每日 digest，两个模型分别生成，并排对比分类、去重、摘要与「概念观察」质量。",
           "> DeepSeek 方复用当天正式 digest；Claude 方按相同流水线现抓候选重跑"
           f"（{cl_kept} 条候选，候选集与 DeepSeek 那次可能略有出入）。", "",
           f"## 🟦 DeepSeek — `{ds_label}`", "", demote_headings(ds_body), "",
           f"## 🟩 Claude — `{cl_label}`", ""]
    body = demote_headings(cl_body)
    if cl_unreachable:
        body += f"\n\n_本方未覆盖：{', '.join(cl_unreachable)}（RSS 错误/超时）。_"
    out += [body, "", "---",
            "_对比说明：两栏均为原创摘要并附原文链接，未复制原文。仅供观察不同模型在同一"
            "任务上的分类粒度、去重合并、摘要笔法与概念抽取差异，非排名。_"]
    return "\n".join(out) + "\n"


def git_commit_push(date_str: str) -> None:
    def run(*a: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True)

    run("add", "evals")
    if run("diff", "--cached", "--quiet").returncode == 0:
        print("（无改动可提交，跳过 commit）")
        return
    if run("commit", "-m", f"eval: {date_str} deepseek vs claude").returncode != 0:
        print("⚠ commit 失败")
        return
    print("✅ 已 commit" if run("push").returncode != 0 else "✅ 已 commit 并 push")


def main() -> int:
    ap = argparse.ArgumentParser(description="模型测评：DeepSeek vs Claude 对比")
    ap.add_argument("--date", default=None, help="日期 YYYY-MM-DD（默认今天北京时间）")
    ap.add_argument("--hours", type=int, default=24, help="Claude 方 RSS 回溯窗口")
    ap.add_argument("--max-items", type=int, default=60,
                    help="Claude 方候选上限（默认 60，控请求体避免网关 524 超时）")
    ap.add_argument("--body-chars", type=int, default=300,
                    help="Claude 方每条正文摘录字数（默认 300；设 0 则只用标题）")
    ap.add_argument("--commit", action="store_true", help="生成后 git add/commit/push")
    args = ap.parse_args()

    llm_client.load_dotenv()
    date_str = args.date or dt.datetime.now(BEIJING).strftime("%Y-%m-%d")

    ds_label, ds_body = deepseek_side(date_str)
    print(f"✅ [DeepSeek] 复用 digests/{date_str}.md（{ds_label}）")
    try:
        cl_label, cl_body, cl_kept, cl_unreach = claude_side(
            date_str, args.hours, args.max_items, args.body_chars)
    except llm_client.LLMError as e:
        print(f"✗ Claude 生成失败：{e}")
        return 1

    md = render_eval(date_str, ds_label, ds_body, cl_label, cl_body, cl_kept, cl_unreach)
    EVALS.mkdir(parents=True, exist_ok=True)
    out_path = EVALS / f"{date_str}.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"✅ 已写入 {out_path.relative_to(ROOT)}")

    if args.commit:
        git_commit_push(date_str)
    else:
        print("（未加 --commit，未提交 git）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
