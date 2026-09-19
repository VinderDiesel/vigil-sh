# vigil-collector-langfuse

Vigil collector plugin for [Langfuse](https://langfuse.com). **Tier: maintained.**

Vigil 吃 Langfuse 的导出，不替代 Langfuse。这个插件只做一件事：把 Langfuse 的 observation 变成 Vigil 的 `CanonicalEvent`。

## 安装

```bash
pip install vigil-collector-langfuse          # 仅文件模式
pip install "vigil-collector-langfuse[api]"   # 含 API 模式（需要 httpx）
```

## 用法

```bash
# 文件模式：解析 Langfuse 导出（JSON 或 JSONL）
vigil collect export.json --collector langfuse --out collected.json

# 带原始 I/O（默认只留摘要，含 PII 风险，慎用）
vigil collect export.json --collector langfuse \
  --options '{"include_io": true}' --out collected.json

# API 模式：直接拉取
export LANGFUSE_PUBLIC_KEY=pk-...
export LANGFUSE_SECRET_KEY=sk-...
vigil collect "langfuse://cloud.langfuse.com" \
  --collector langfuse --options '{"since": "2026-09-01", "limit": 200}'
```

## 隐私默认

`input` / `output` 是 trace 里 PII 最密集的部分。默认只产出 `prompt_digest` 与 `completion_digest`（SHA-256，不可逆，够做血缘与去重）。
`include_io=true` 才会带上原文，且下游 minimizer 仍会按白名单与正则清洗。

## 映射规则

| Langfuse `type` | CanonicalEvent `kind` |
|---|---|
| `GENERATION` / `EMBEDDING` | `llm.call` |
| `SPAN` / `TOOL` / `RETRIEVER` / `EVALUATOR` / `GUARDRAIL` | `tool.call` |
| `EVENT` | `tool.result` |
| `AGENT` / `CHAIN` | `run.start` |
| `level=ERROR` 且有 `statusMessage` | `error` |

`effect_class` 由工具名启发式判定（delete/支付类 → `destructive`），未识别一律 `unknown`，下游按"潜在破坏性"处理。

## 合规

插件通过 `vigil.conformance.assert_collector_contract`（确定性、有序、类型正确）。
`httpx` **只在函数内部导入**，违反 HARD-4 的顶层导入会让它无法在无依赖环境下使用。

## 许可

MIT。
