# evals/ — 模型测评层

同一天的每日 digest，用不同模型各生成一版，**并排对比**分类粒度、去重合并、摘要笔法
与「概念观察」的抽取质量。和 `digests/` 一样，**markdown 是唯一事实来源**，
`web/build.py` 只做渲染（「模型测评 Eval」tab）。

## 怎么生成

```bash
# 复用当天 digests/YYYY-MM-DD.md 作为 DeepSeek 方，用 Claude 现抓候选补跑一版
python3 scripts/build_eval.py                 # 今天
python3 scripts/build_eval.py --date 2026-07-10
python3 scripts/build_eval.py --commit        # 生成后 add/commit/push
```

- **DeepSeek 方**：直接复用已生成的 `digests/YYYY-MM-DD.md` 正文（不重跑，省一次调用）。
- **Claude 方**：按 `generate_digest.py` 的同一条流水线现抓 RSS + 公开正文、调 Claude
  生成正文。候选来自当次 RSS，可能与 DeepSeek 那次略有出入（可接受的对比误差）。
- 前置：`.env` 里 DeepSeek 和 Claude 两个 provider 的 key 都要就绪（见 `.env.example`）。

## 文件格式

`evals/YYYY-MM-DD.md`：H1 标题 + front-matter 说明，正文两大段——
`## 🟦 DeepSeek — <模型>` 和 `## 🟩 Claude — <模型>`，各自内部是降一级的五大类分区
（`### 政治·国际` …）+ `### 📚 概念观察`。

## 版权红线（同 instruction.md §2）

两栏都只写**原创中文摘要 + 附原文链接**，不复制原文、不绕过付费墙。抓来的公开正文
只用于喂 LLM 理解，**不入库**。这是一个**对比观察**产出，不是排名或评分。
