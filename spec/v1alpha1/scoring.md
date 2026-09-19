# Spec v1alpha1 — Scoring（评分与弃权）

## 1. JudgeVerdict 结构

| 字段 | 说明 |
|---|---|
| `judge` / `judge_version` | 评分器标识与版本，必带 |
| `score` | `float` 或 `None` |
| `confidence` | 0.0–1.0 |
| `abstain` | **弃权**，一等公民 |
| `rationale` | 人类可读理由 |
| `prompt_digest` | LLM judge 的 prompt 摘要（用于检测漂移） |
| `evidence_refs` | 证据指针 |

## 2. 规则

1. **弃权优先于猜测**：没有可靠意见就 `abstain=True`。禁止把 `None` 当 0 分（HARD-5）。
2. **确定性优先**：能用确定性 scorer 判定的用例，不要用 LLM judge——那只是白白引入方差。
3. **分歧是信号**：多个 scorer 不一致时，记 `disagreement = max-min`，≥0.34 或结论为 UNDETERMINED ⇒ `needs_review`，送人工队列。
4. **禁止静默取均值**：最终分不是平均分，是**分歧报告**。
5. **评分器崩溃 ⇒ 弃权 + 告警**，不得中断整个套件。
6. **ERROR 只能由 runner 设置**（执行本身崩溃），Agent 自报 outcome 不得否决或伪造判定。

## 3. 结果合并

| 情况 | 结果 |
|---|---|
| 执行抛异常 | `ERROR` |
| 环境未验证 | `UNDETERMINED` |
| 无可用（非弃权）判定 | `UNDETERMINED` |
| 全部判定通过 | `PASS` |
| 全部判定不通过 | `FAIL` |
| 判定不一致 | `UNDETERMINED` + `needs_review` |

## 4. Meta-eval（v0.2，契约先定）

`vigil audit-judge` 计划输出：与人工标注的一致性、自洽性（同例多次运行）、版本间漂移、长度/格式偏见。

**前提**：标注集必须独立于日常生产数据，否则等于用同一个模型循环验证自己。v1alpha1 尚未提供该命令，不得以任何半成品形式引入。
