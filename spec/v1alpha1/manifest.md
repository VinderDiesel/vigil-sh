# Spec v1alpha1 — CaseManifest

用例不是"一个 prompt 加一个期望答案"，而是一份**执行契约**：环境、种子、mock、允许的副作用、oracle 版本、证据来源，缺一不可。

## 1. 必填与校验

- `spec_version` **必填**，当前唯一合法值 `v1alpha1`；未知版本直接抛错，禁止静默兼容（HARD-2）。
- `case_id` 稳定可读，建议 `case:<slug>`；内容寻址 hash 单独存于 `canonical_hash`。
- `oracle` 非空。Vigil **不自动生成 oracle**；未经人工评审的用例 `confidence ≤ 0.3`。

## 2. 字段

| 字段 | 说明 |
|---|---|
| `input` | 输入（通常来自 trace 的用户侧输入） |
| `oracle` | 判定依据：`exact` / `contains` / `not_contains` / `regex` |
| `oracle_version` | oracle 变更必须升版本；门禁按版本锁定 |
| `env` | `EnvironmentContract`（见下） |
| `replay_mode` | 五种模式之一，决定允许使用的措辞 |
| `provenance` | `collector`、`source_ref`（**只放引用，不放原文**）、`redactions`、`reviewed_by` |
| `severity` | `critical/high/medium/low/unknown` |
| `labels` | 业务域、安全标签等 |
| `confidence` | oracle 正确的置信度；低置信度用例不阻断构建 |
| `expires_at` | 过期用例不得参与门禁（用例会腐化）。取值为 ISO 8601 日期（`YYYY-MM-DD`）；**解析失败或为空的取值一律视为"已过期"**（保守降级，同 HARD-6） |
| `raw_hash` / `canonical_hash` / `cluster_id` | 见 event.md 三层标识 |

## 3. EnvironmentContract

| 字段 | 默认 | 说明 |
|---|---|---|
| `image` | null | 环境镜像（快照/沙箱模式必填） |
| `init_snapshot` | null | 初始快照引用 |
| `network_policy` | `none` | `none` / `allowlist` / `open` |
| `allowlist` | [] | 允许的域名 |
| `tool_mock_map` | {} | 工具 → 录制响应引用 |
| `seeds` | {} | 随机种子、模型 temperature |
| `clock_policy` | `frozen` | 时间冻结策略 |
| `side_effect_policy` | `dry-run` | `dry-run` / `mock` / `live` |
| `env_vars` | {} | 环境变量（不得含 secret 明文） |

**没有该契约的重跑只能叫 best-effort rerun，不能叫 replay。**

## 4. 五种重放模式

| 模式 | 可用"重放"措辞 | 典型适用 |
|---|:--:|---|
| `record-only` | ❌ | 纯审计 |
| `mock-replay` | ✅ | 工具响应来自录制 |
| `snapshot-replay` | ✅ | 有快照边界 |
| `sandbox-execute` | ✅ | 受控环境真实执行 |
| `live-canary` | ❌ | 仅契约检查 |

## 5. 生命周期

`collect → select → mint(confidence=0.3) → 人工评审(1.0) → run → gate → 到期/失效`

- 用例腐化是默认状态，不是异常：模型、工具 schema、业务规则变了，oracle 就变了。
- 到期用例保留用于分析，但不参与门禁决策。
- `oracle_ambiguous`（用例本身错）是合法失败分类，用于把误报变成可统计、可修正的对象。
