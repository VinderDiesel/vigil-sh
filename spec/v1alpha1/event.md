# Spec v1alpha1 — Canonical Event

规范化事件是 Vigil 唯一理解的执行单元。厂商 trace（OTel span、OpenInference、Langfuse observation、自定义 JSONL）必须先被 collector 映射到本结构，才能进入下游任何环节。

## 1. 三层表示与三个标识

| 层 | 内容 | 标识 | 用途 |
|---|---|---|---|
| raw | 原样摄入的字节 | `raw_hash` | 审计："我们当初收到了什么" |
| canonical | 规范化 + 声明式脱敏后 | `canonical_hash` | 身份、缓存、去重（**仅在字节层**） |
| cluster | 语义分组结果 | `cluster_id` | **仅供参考**，永不作为身份或去重依据（HARD-3） |

规范化序列化规则（`vigil/cas.py`）：`sort_keys` + 无空白分隔符 + `ensure_ascii` + `allow_nan=False`。任何偏离都会破坏可复现性。

## 2. 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `event_id` | str | 来源系统内的唯一 ID |
| `run_id` | str | 同一次执行共享 |
| `parent_id` | str\|null | 层级关系 |
| `seq` | int | 单调序号 |
| `ts` | str | RFC3339 UTC |
| `kind` | enum | `run.start` / `run.end` / `llm.call` / `tool.call` / `tool.result` / `state.checkpoint` / `human.handoff` / `error` / `unknown` |
| `name` | str | 工具名 / 模型名 / span 名 |
| `payload` | dict | 自由结构；Vigil 只拥有信封与安全标签，不拥有框架语义 |
| `effect_class` | enum | `read` / `write` / `destructive` / `unknown` |
| `observed` | bool | `false` = 采集器存在可见性缺口 |
| `meta` | dict | 采集器私有信息，同样受最小化约束 |

## 3. 不变量

1. **不伪造**：采集器不得生成它没看到的事件；缺失时置 `observed=false`（对应失败分类 `unobserved_side_effect`）。
2. **不重取**：采集器不得为了补全而重新访问外部资源。
3. **不落盘原始字节**：写盘必须经过 minimizer。
4. **排序确定性**：以 `(seq, ts, event_id)` 排序，绝不依赖到达顺序。
5. **未知即危险**：`effect_class=unknown` 一律按潜在破坏性处理。

## 4. 最小化（minimizer_default）

- 默认拒绝：`payload` 顶层字段仅保留白名单（`tool`、`arguments`、`status`、`error`、`model`、`*_digest`、`usage`、`duration_ms`、`return_shape` …）。
- 字段名命中 `password/secret/token/api_key/authorization/cookie/credential/private_key` ⇒ 整字段 `[REDACTED]`。
- 字符串内命中 email / 手机号 / 身份证 / 卡号 / IPv4 / JWT / API key / 私钥头 ⇒ 替换为 `[REDACTED]`。
- 每次移除写入 `redactions`，保持可审计。
- 幂等：对已最小化事件再跑一次，结果必须逐字节相同（conformance 强制）。
