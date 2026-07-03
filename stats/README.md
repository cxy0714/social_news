# stats/ — 统计数据

## usage.jsonl（可选，token 用量）

统计页（`/stats.html`）默认只显示**构建脚本能客观数出来的产量**：候选条数、
条目数、来源链接数、产出字数、覆盖天数。这些不涉及任何 token，构建时从 digest
markdown 直接统计，可复现。

如果想额外展示**每期生成消耗的 token**，在本目录放一个 `usage.jsonl`，每行一条
JSON 记录，按日期对应：

```jsonl
{"date": "2026-07-03", "input_tokens": 128000, "output_tokens": 6200}
{"date": "2026-07-02", "input_tokens": 131500, "output_tokens": 5900}
```

- `date` 必填，格式 `YYYY-MM-DD`，与 `digests/YYYY-MM-DD.md` 对应。
- `input_tokens` / `output_tokens` 为整数；缺失的字段在表格里显示 `—`。
- 文件不存在时，统计页正常工作，只是不显示 token 两列。

### token 数据从哪来

`web/build.py` **不消耗 token**——它只是把 markdown 渲染成 HTML。真正烧 token 的
是云端 Claude 从 `_raw-*.md` 候选 → 写出 `digests/YYYY-MM-DD.md` 那一步（LLM 生成）。
因此 token 数据需要外部来源，两种方式：

1. **云端自记录**：在 `instruction.md` 工作流里加一步，生成 digest 后把本次估算的
   input/output token 追写进 `stats/usage.jsonl` 并一并 commit。（Claude 自估，
   不精确但有趋势。）
2. **事后回填**：从 Anthropic 后台的 usage 数据按日期手动/脚本回填。

`usage.jsonl` 已加入版本控制（不像 `_raw-*.md` 那样 gitignore），因为它是要展示的
真实数据。
