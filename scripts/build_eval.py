#!/usr/bin/env python3
"""模型测评：同一天的 digest，两栏并排对比，写入 evals/YYYY-MM-DD.md。

- 复用方：直接读已生成的 `digests/YYYY-MM-DD.md` 正文（不重跑，省一次调用），标签按
  该 digest 头部的「由 <模型> 分类」如实标注。
- 现跑方：按 generate_digest.py 同一条流水线取候选（`--from-raw` 则复用当天
  `digests/_raw-DATE.md`，与复用方吃同一份材料）→ 调 `--fresh-provider` 指定的后端。

默认是「DeepSeek 复用 + Claude 现跑」；加了 `--fresh-provider deepseek-official`（配上
`--from-raw`）就是「Claude 复用 + 官方 DeepSeek 现跑」，两栏都写进 🟦 DeepSeek / 🟩 Claude
两个标题下，用于看模型差异。

产出 `evals/YYYY-MM-DD.md` 是入库 markdown（唯一事实来源），网页层 web/build.py
渲染成「模型测评」tab。守版权红线：正文只喂 LLM，产出仍是原创摘要+链接。

用法：
    python3 scripts/build_eval.py                    # 今天：复用 DeepSeek 版，现跑 Claude
    python3 scripts/build_eval.py --date 2026-07-10
    python3 scripts/build_eval.py --fresh-provider deepseek-official --from-raw
                                                     # 今天：复用当天 digest，官方 flash 同材料现跑
    python3 scripts/build_eval.py --commit           # 生成后 add/commit/push
仅标准库，Python 3.9+。
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

try:
    from . import generate_digest as gd
    from . import llm_client
except ImportError:  # 直接作为脚本运行时，回退到同目录导入
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


def reused_side(date_str: str) -> tuple[str, str]:
    """复用当天已生成的 digests/YYYY-MM-DD.md 作为一栏，返回 (标签, 正文)。

    标签从 digest 头部的「由 <模型> 分类」里抠出来，所以那天是谁生成的就如实标谁——
    正式 digest 现在可能出自交大网关、官方 API 或 Claude 任意一家。"""
    path = gd.DIGESTS / f"{date_str}.md"
    if not path.exists():
        raise SystemExit(f"找不到 {path.relative_to(ROOT)}（先跑 generate_digest.py 生成正式 digest）")
    md = path.read_text(encoding="utf-8")
    m = re.search(r"由 (\S+?) 分类", md)
    label = m.group(1) if m else "unknown"
    return label, extract_digest_body(md)


def fresh_side(provider: str, date_str: str, hours: int, max_items: int, body_chars: int,
               from_raw: bool = False) -> tuple[str, str, int, list[str]]:
    """现跑一栏：取候选（或复用当天 _raw 清单）+ 调指定 provider。返回 (标签, 正文, 候选数, 不可达源)。

    from_raw=True 时直接读 digests/_raw-DATE.md（标题/来源/地区/正文摘录都在里面），
    于是两栏吃的是**同一份材料**，差异只来自模型本身；否则按 daily 的流水线现抓 RSS
    （走 Anthropic 网关时单请求约 100s 上限，故默认候选/正文都取更小的规模）。"""
    unreachable: list[str] = []
    raw = gd.raw_path_for(date_str)
    if from_raw and raw.exists():
        items = gd.load_raw_candidates(raw)
        print(f"→ [{provider}] 复用候选清单 {raw.relative_to(ROOT)}（{len(items)} 条，与另一栏同材料）")
    else:
        if from_raw:
            print(f"  ⚠ 没有 {raw.name}，改为现抓 RSS。")
        print(f"→ [{provider}] 抓 RSS 候选（过去 {hours}h）…")
        items, unreachable = gd.collect_candidates(hours, max_items)
        print(f"  候选 {len(items)} 条；不可达 {len(unreachable)} 个")
        if body_chars > 0:
            print(f"→ [{provider}] 抓公开正文摘录（每条 ≤{body_chars} 字，仅喂 LLM）…")
            for it in items:
                it["body"] = gd.fetch_body(it["link"], limit=body_chars)
    print(f"→ [{provider}] 调用 {llm_client.provider_label(provider)} 分类去重+摘要…")
    data = llm_client.chat_json(gd.SYSTEM_PROMPT, gd.build_user_payload(items, date_str),
                                providers=[provider])
    return llm_client.model_label(), gd.render_body(data), len(items), unreachable


def _side_name(label: str) -> str:
    """把 provider 标签翻成栏目名：deepseek@sjtu:... → DeepSeek · 交大网关。

    两栏可能同属 DeepSeek 家族（网关 vs 官方），标题必须说清是哪条腿。"""
    if label.startswith("claude"):
        return "Claude"
    if label.startswith("gpt"):
        return "GPT"
    if "@sjtu" in label:
        return "DeepSeek · 交大网关"
    if "@official" in label:
        return "DeepSeek · 官方"
    if label.startswith("deepseek"):
        return "DeepSeek"
    return label or "模型"


def render_eval(date_str: str, ds_label: str, ds_body: str, cl_label: str, cl_body: str,
                note: str, ds_tail: str = "", cl_tail: str = "") -> str:
    """两栏并排的 evals 页。note 写进 front-matter（两栏各自怎么来的），
    ds_tail/cl_tail 是追加到该栏末尾的斜体注（如「本方未覆盖：…」）。"""
    out = [f"# 模型测评 · {date_str}",
           f"> 生成时间：{date_str}（北京时间）",
           "> 同一天的每日 digest，两个模型分别生成，并排对比分类、去重、摘要与「概念观察」质量。",
           f"> {note}", "",
           f"## 🟦 {_side_name(ds_label)} — `{ds_label}`", "", demote_headings(ds_body) + ds_tail, "",
           f"## 🟩 {_side_name(cl_label)} — `{cl_label}`", "", demote_headings(cl_body) + cl_tail, "",
           "---",
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
    ap = argparse.ArgumentParser(description="模型测评：同一天的 digest 两栏并排对比")
    ap.add_argument("--date", default=None, help="日期 YYYY-MM-DD（默认今天北京时间）")
    ap.add_argument("--fresh-provider", choices=["claude", "deepseek", "deepseek-official"],
                    default="claude",
                    help="现跑的那一栏用哪个后端（默认 claude）；选 deepseek 系时，"
                         "当天正式 digest 归 Claude 栏（适合 digest 本身就是 Claude 生成的）")
    ap.add_argument("--from-raw", action="store_true",
                    help="现跑的一栏复用 digests/_raw-YYYY-MM-DD.md，与另一栏吃同一份材料，不再抓 RSS")
    ap.add_argument("--hours", type=int, default=24, help="现跑一栏的 RSS 回溯窗口（未用 --from-raw 时）")
    ap.add_argument("--max-items", type=int, default=60,
                    help="现跑一栏的候选上限（默认 60，控请求体避免 Claude 网关 524 超时；"
                         "--from-raw 时忽略）")
    ap.add_argument("--body-chars", type=int, default=300,
                    help="现跑一栏每条正文摘录字数（默认 300；设 0 则只用标题；--from-raw 时忽略）")
    ap.add_argument("--note-extra", default=None,
                    help="往 front-matter 追加一行说明（例如本次两栏差在 prompt 的哪一处）")
    ap.add_argument("--commit", action="store_true", help="生成后 git add/commit/push")
    args = ap.parse_args()

    llm_client.load_dotenv()
    date_str = args.date or dt.datetime.now(BEIJING).strftime("%Y-%m-%d")

    reused_label, reused_body = reused_side(date_str)
    print(f"✅ [复用] digests/{date_str}.md（{reused_label}）")
    fresh = args.fresh_provider
    try:
        fresh_label, fresh_body, fresh_kept, fresh_unreach = fresh_side(
            fresh, date_str, args.hours, args.max_items, args.body_chars, from_raw=args.from_raw)
    except llm_client.LLMError as e:
        print(f"✗ {fresh} 生成失败：{e}")
        return 1
    print(f"✅ [现跑] {fresh_label}（{fresh_kept} 条候选）")

    where = ("复用当天候选清单 _raw，与另一栏同材料" if args.from_raw
             else f"当次现抓 RSS（{fresh_kept} 条候选，与另一栏可能有出入）")
    tail = f"\n\n_本方未覆盖：{', '.join(fresh_unreach)}（RSS 错误/超时）。_" if fresh_unreach else ""
    if fresh == "claude":
        ds_label, ds_body = reused_label, reused_body
        cl_label, cl_body = fresh_label, fresh_body
        ds_tail, cl_tail = "", tail
        note = f"DeepSeek 方复用当天正式 digest；Claude 方按相同流水线重跑（{where}）。"
    else:
        ds_label, ds_body = fresh_label, fresh_body
        cl_label, cl_body = reused_label, reused_body
        ds_tail, cl_tail = tail, ""
        note = (f"左栏 {fresh_label} 按 generate_digest.py 同一流水线重跑（{where}）；"
                f"右栏复用当天正式 digest（{reused_label}）。")
        if fresh_label == reused_label:
            note += "两栏是**同一个端点**，差异来自 prompt 或运行参数，而非模型本身。"
        elif reused_label.startswith("deepseek"):
            note += "两栏同为 DeepSeek，比的只是端点。"
    if args.note_extra:
        note += "\n> " + args.note_extra.strip()

    md = render_eval(date_str, ds_label, ds_body, cl_label, cl_body, note, ds_tail, cl_tail)
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
