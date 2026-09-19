# 架构说明

## 1. 定位：可靠性资产的控制面

Vigil 不争夺基础设施层（OTel collector、trace store、沙箱）与集成层（框架 SDK、CI），它占据的是**资产层**：case、contract、manifest、score、SLO、签名与门禁决策。

```
┌─────────────── 集成层（别人做） ───────────────┐
│ 框架 SDK · MCP · CI · 可观测平台导出            │
└──────────────────────┬───────────────────────┘
                       ▼
┌─────────────── 资产层（Vigil） ───────────────┐
│ CanonicalEvent → CaseManifest → Score → Gate   │
└──────────────────────┬───────────────────────┘
                       ▼
┌─────────────── 基础设施层（别人做） ───────────┐
│ 对象存储 · 容器 · K8s · Proxmox · 快照后端      │
└───────────────────────────────────────────────┘
```

这样划分的收益：不复制 Langfuse/Phoenix 的存储与 UI，不复制 Inspect/Orchard 的环境实现，也不与 Microsoft AGT 在治理执行层正面竞争。

## 2. 核心链路与模块

| 阶段 | 模块 | 产物 |
|---|---|---|
| collect | `plugins/collector_file` / `collector_otel` / 外部包 `langfuse` | `CanonicalEvent[]` |
| minimize | `plugins/minimizer_default.py` | 脱敏事件 + `redactions` |
| select | `plugins/selector_rules.py` | 候选 run（含触发信号） |
| mint | `models/case.py` + `cli.mint` | `CaseManifest` |
| run | `runner.py` + `envbase` + `plugins/env_noop` / 外部包 `docker` | `RunResult` |
| score | `plugins/scorer_*` → `models/result.py` | `JudgeVerdict[]` |
| aggregate | `runner.aggregate` | `Aggregate` |
| gate | `plugins/gate_hard.py` → `models/gate.py` | `GateDecision` |
| report | `artifacts.py` | JUnit / JSON / PR 评论 |

## 3. 关键设计决策与理由

| 决策 | 理由 |
|---|---|
| 核心零第三方依赖 | `pip install` 即可跑；传播成本决定早期生死 |
| CLI 用 stdlib argparse | 同上；重型 CLI 框架放插件侧 |
| 插件经 entry points 发现，内置无特权路径 | 内置插件若腐化，示范效应比第三方更糟 |
| `spec_version` 强校验 | 静默 schema 漂移是最难查的 bug |
| 三层哈希分离 | 用语义簇去重会删掉最稀有的失败 |
| Judge 可弃权 + 分歧度上报 | LLM-as-Judge 漂移是头号公敌 |
| 环境未验证 ⇒ UNDETERMINED | 无验证的 PASS 比 FAIL 更有害 |
| 硬门禁与软阈值分离 | 统计豁免安全阈值等于没有阈值 |
| UNDETERMINED 在 JUnit 中记为 skipped | "沉默"是 flake 藏身之处 |
| v1alpha1 不实现统计门禁 | 半成品门禁会训练团队重跑 CI 直到变绿 |

## 3.1 核心 vs 外部包

| 能力 | 位置 | 外部依赖 |
|---|---|---|
| `file` / `otel` 采集、最小化、选择、`noop` 环境、确定性评分、硬门禁 | **core** | 无（stdlib） |
| `langfuse` 采集 | `packages/vigil-collector-langfuse` | httpx（可选，函数内导入，仅 API 模式） |
| `docker` 环境 | `packages/vigil-env-docker` | Docker daemon（shell 调 CLI） |

判定标准只有一条：**核心必须 `pip install vigil` 即可运行**。任何 SDK 或 daemon 需求都进外部包。

## 3.2 环境能力契约

环境声明 `capabilities`，由 `vigil.envbase.enforce` 统一判定。请求超出能力即 `CapabilityError`
→ runner 降级 `UNDETERMINED`。`clock_policy=frozen` 是唯一建议性能力（缺失只告警）。
详见 `spec/v1alpha1/environment.md` 与 RFC 0003。

## 3.3 跨边界执行

进程内环境直接调用 callable；容器/远程环境通过 `vigil.harness`：

```
case.json + agent.py (只读挂载) → python -m vigil.harness → RunResult JSON (stdout)
```

## 4. 依赖方向

`collector → minimizer → selector → environment → scorer → gate`，单向。
插件可依赖 `vigil.models.*` 与 `vigil.cas`；禁止插件间互相 import 实现；跨层需求走 manifest。

## 5. 失败优先的设计

所有环节的默认状态是"不确定"，而不是"通过"：

- 采集有缺口 → `observed=false` → 分类 `unobserved_side_effect`
- oracle 缺失 → scorer 弃权 → `UNDETERMINED`
- 评分器崩溃 → 弃权 + 告警，套件继续
- 环境恢复失败 → `UNDETERMINED`，不产出 PASS
- 执行抛异常 → `ERROR`，任何判定都无法掩盖

## 6. 演进路线

见 README §8 的决策门（G1–G4）。架构上的预留：

- `EnvironmentProvider` 已定义 `provision/restore/teardown`，v0.2 的 docker 环境只需实现该 SPI。
- `Scorer` 返回 `JudgeVerdict`，v0.2 的 LLM judge 与 `audit-judge`（meta-eval）无需改协议。
- `Gate.decide(aggregate, slos)` 已接受 SLO 列表，v0.2 的统计门禁可新增插件而不改签名。
