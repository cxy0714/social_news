# evals/ — 模型测评层

同一天的每日 digest，用不同模型各生成一版，**并排对比**分类粒度、去重合并、摘要笔法
与「概念观察」的抽取质量。和 `digests/` 一样，**markdown 是唯一事实来源**，
`web/build.py` 只做渲染（「模型测评 Eval」tab）。

## 怎么生成

```bash
# 默认：复用当天 digests/YYYY-MM-DD.md 作为 DeepSeek 方，用 Claude 现抓候选补跑一版
python3 scripts/build_eval.py                 # 今天
python3 scripts/build_eval.py --date 2026-07-10
python3 scripts/build_eval.py --commit        # 生成后 add/commit/push

# 反过来：当天 digest 是 Claude 生成的，就用官方 DeepSeek 同材料现跑一版
python3 scripts/build_eval.py --fresh-provider deepseek-official --from-raw
python3 scripts/build_eval.py --fresh-provider deepseek --from-raw   # 交大网关
```

- **复用方**：直接读已生成的 `digests/YYYY-MM-DD.md` 正文（不重跑，省一次调用），标签按
  该 digest 头部的「由 `<模型>` 分类」如实标注，所以谁生成的都不会被认错。
- **现跑方**：按 `generate_digest.py` 的同一条流水线取候选 + 调 `--fresh-provider` 指定的
  后端生成正文。默认现抓 RSS（候选可能与另一栏略有出入，见 `--max-items` /`--body-chars`）；
  加 `--from-raw` 则复用 `digests/_raw-YYYY-MM-DD.md`，**两栏吃同一份材料**，差异只来自模型
  —— 想干净地比较模型时用这个（当天的 `_raw` 是本地私有中间产物，不入库）。
- 两栏固定写在 `## 🟦 DeepSeek` / `## 🟩 Claude` 之下：现跑方是 deepseek 系时它占 DeepSeek
  栏、复用的 digest 归 Claude 栏；现跑方是 claude 时反之。
- 前置：`.env` 里对应 provider 的 key 要就绪（见 `.env.example`）。

## 文件格式

`evals/YYYY-MM-DD.md`：H1 标题 + front-matter 说明，正文两大段——
`## 🟦 <左栏> — <模型标签>` 和 `## 🟩 <右栏> — <模型标签>`，各自内部是降一级的五大类分区
（`### 政治·国际` …）+ `### 📚 概念观察`。

栏目名按实际端点取，常见的有 `DeepSeek`、`DeepSeek · 交大网关`、`DeepSeek · 官方`、
`Claude`、`GPT`；左栏固定 🟦、右栏固定 🟩。**两栏可以同属 DeepSeek 家族**（网关 vs 官方），
这时比的就是端点质量而非模型家族——正是为了检验「交大网关的 deepseek-chat 靠不靠得住」。

## 版权红线（同 instruction.md §2）

两栏都只写**原创中文摘要 + 附原文链接**，不复制原文、不绕过付费墙。抓来的公开正文
只用于喂 LLM 理解，**不入库**。这是一个**对比观察**产出，不是排名或评分。
