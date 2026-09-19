# Vigil（衡鉴）

**把 Agent 的一次执行，变成可重放、可评分、可进 CI 门禁的可靠性资产。**

Vigil 不是追踪平台，不是基准榜单，也不是又一个 LLM 评测框架。它是连接"生产证据"和"工程门禁"的那一层：吃现有可观测平台的导出，产出版本化的回归用例，用受控环境重放，用多评分器判定，最后在 CI 里给出可执行的放行/阻断决策。

> **状态**：v0.1.0-alpha，规范版本 `v1alpha1`。协议未冻结，勿用于关键生产决策。
> **许可**：MIT。

---

## 一、我们明确不做什么

这些边界比功能列表更重要。越界一次，项目就会掉进一个已经有强手的战场。

| 不做 | 原因 | 该用谁 |
|---|---|---|
| 追踪 / 可观测 UI | Langfuse、LangSmith、Phoenix 已经做得很好 | 它们是 Vigil 的**输入源** |
| 自建基准榜单 | 烧钱且同质化 | SWE-bench、τ²-bench、OSWorld、GAIA |
| 通用评测 runner | Inspect、DeepEval、Promptfoo 已覆盖 | 复用为 scorer / 执行后端 |
| Agent 运行时治理 | Microsoft AGT 正从应用层做拦截与审计 | 保持互操作，不替代 |
| LLM Judge 作为唯一裁判 | Judge 会漂移，必须被校准 | 确定性 scorer 优先 |
| **"任意执行都能确定性重放"** | **做不到，不承诺** | 见下方五种重放模式 |

**Vigil 的差异化不在原子能力，而在资产链**：`执行 → 规范化事件 → 用例契约 → 评分 → 门禁产物`。这条链目前没有开放、可移植、可审计的实现。

---

## 二、核心链路

```
  Execution          CanonicalEvent         CaseManifest          Score            GateArtifact
 (任意来源)    →    (规范化+脱敏)     →    (版本化契约)    →   (评分+弃权)   →   (JUnit/JSON)
       ▲                                        │
       └────────────  replay ────────────────────┘
```

| 环节 | 产物 | 关键约束 |
|---|---|---|
| collect | `CanonicalEvent[]` | 三层哈希：`raw_hash` / `canonical_hash` / `cluster_id` 永不混用 |
| minimize | 脱敏后的事件 | **默认拒绝**：未知字段丢弃，已知字段内 PII 打码 |
| select | 候选 run 列表 | 规则驱动、可复现；v1alpha1 **不做语义去重**（会删掉最稀有的失败） |
| mint | `CaseManifest` | oracle 必须人工提供；未评审的用例 `confidence=0.3` |
| run | `RunResult` + 产物 | 环境不可验证 ⇒ 结果强制 `UNDETERMINED` |
| gate | `GateDecision` | 硬门禁（安全/合规）永不豁免；统计门禁 v1alpha1 未提供 |

---

## 三、五种重放模式（承诺边界）

"可重放"是有层次的。Vigil 要求每个用例**显式声明**自己属于哪一类，并在 CLI 里如实打印允许使用的措辞。

| 模式 | 适用 | 可以用"重放"这个词吗 |
|---|---|---|
| `record-only` | 只审计，不重跑 | ❌ 只能说"记录" |
| `mock-replay` | 工具响应来自录制 | ✅ |
| `snapshot-replay` | 有 fs/db/容器快照 | ✅（在快照边界内） |
| `sandbox-execute` | 受控环境内真实执行 | ✅ |
| `live-canary` | 外部状态持续变化 | ❌ 只能说"契约检查" |

真实资金、删除、发邮件、撤销权限等**不可逆副作用**默认 `dry-run`，需要 `live` 必须由环境插件提供能力，且用例 YAML 不能自我提权。

---

## 四、快速开始（约 5 分钟，无需 Docker / 云 / 模型 Key）

```bash
pip install -e ".[dev]"

# 可选：独立发行包（见 packages/）
pip install -e "packages/vigil-collector-langfuse"   # langfuse 采集
pip install -e "packages/vigil-env-docker"           # 容器环境

# 1) 看已安装插件
vigil plugins

# 2) 采集并脱敏一条 trace（JSONL / OTLP / Langfuse 导出 → 规范化事件）
vigil collect examples/minimal-agent/trace.jsonl --out collected.json
vigil collect examples/otel-export/trace.otlp.json --collector otel --out otel.json

# 3) 按策略挑选值得变成用例的 run
vigil select examples/minimal-agent/trace.jsonl --options '{"signals":["failure","destructive"]}'

# 4) 造一条用例（oracle 必填，自动造 oracle 不在范围内）
vigil mint --case-id case:demo --input '{"question":"refund-policy"}' \
           --oracle '{"contains":["14 days"]}' --out cases/demo.json

# 5) 跑套件，产出 JUnit + JSON + PR 评论，并用退出码表达门禁
vigil run --cases examples/minimal-agent/cases \
          --agent examples/minimal-agent/agent.py \
          --junit vigil-junit.xml --json vigil-report.json --comment pr-comment.md
echo $?   # 0 = allow, 1 = block
```

自定义 Agent 只需暴露一个函数：

```python
def run(case: CaseManifest) -> RunResult: ...
```

传**文件路径**给 `--agent`，Vigil 会把它包成 `LoadedAgent`：进程内直接调用，
容器/远程环境则把文件挂进沙箱，用 `python -m vigil.harness` 执行（活体 callable 无法穿越进程边界）。

---

## 五、CI 集成示例

```yaml
- name: vigil reliability gate
  run: |
    vigil run --cases cases/ \
              --agent tests/agent_harness.py \
              --env docker \
              --scorer exact,llm \
              --repeats 3 \
              --slo vigil-slo.json \
              --junit vigil-junit.xml --json vigil-report.json --comment pr.md
- name: publish report
  if: always()
  uses: actions/upload-artifact@v4
  with: { name: vigil-report, path: vigil-junit.xml }
```

默认 SLO（`--slo` 未指定时）：

| metric | 阈值 | 类型 |
|---|---|---|
| `policy_violations` | max 0 | **硬** |
| `unrecoverable_rate` | max 0.05 | **硬** |
| `pass_rate` | min 0.90 | 软（仅告警） |
| `p95_cost_usd` | max 0.25 | 软 |
| `flake_rate` | max 0.02 | 软 |

软阈值在 v1alpha1 **不阻断构建**。理由：没有声明最小可检测效应（MDE）的统计门禁，会训练团队反复重跑 CI 直到变绿——那比没有门禁更糟。

---

## 六、失败分类（v1alpha1，仅 8 类）

`tool_argument` · `tool_permission` · `state_transition` · `policy` · `oracle_ambiguous` · `environment_flake` · `model_reasoning` · `unobserved_side_effect`

`oracle_ambiguous`（**用例本身错了**）是一等公民。评测系统最常见的失败不是误判 Agent，而是误判用例。每条用例都带 `confidence` 与 `expires_at`，过期的用例不能参与门禁。

---

## 七、插件体系

六类插件，全部通过 `importlib.metadata` entry points 注册，内置插件与第三方插件走**完全相同**的路径：

| 类别 | 职责 | v0.1 内置 |
|---|---|---|
| `vigil.collectors` | 厂商 trace → 规范事件 | `file`（参考实现）、`otel`（core）；`langfuse`（外部包） |
| `vigil.minimizers` | 脱敏 / 最小化 | `default` |
| `vigil.selectors` | 挑选候选 run | `rules` |
| `vigil.environments` | 环境供给与恢复 | `noop`（core，仅进程内）；`docker`（外部包） |
| `vigil.scorers` | 评分，可弃权 | `exact`、`contains` |
| `vigil.gates` | 放行 / 阻断 | `hard` |

外部包见 [`packages/`](packages/)：需要 httpx / Docker daemon 的能力**不进核心**，
重型依赖一律函数内延迟导入。环境插件必须声明 `capabilities`，由 `vigil.envbase.enforce`
统一拒绝越权请求——**用例 YAML 不能自我提权**。

分层依赖只允许单向：`collector → minimizer → selector → environment → scorer → gate`。跨层需求走 manifest，禁止插件互相 import 实现。

维护分级：`core`（项目维护，semver 保证）/ `maintained`（有具名 owner）/ `community`（无担保，README 明确标注）。

写一个插件：实现对应 Protocol（`vigil/protocol.py`），在 `pyproject.toml` 声明 entry point，然后跑 `pytest conformance/`——**过不了合规测试的插件，不能上架 registry**。

---

## 八、路线与决策门

日期是承诺，不是愿望。每个决策门未通过就收缩范围或转向，**不通过加功能掩盖证据不足**。

| 门 | 时间 | 交付 | 通过门槛 |
|---|---|---|---|
| **G1** | 第 14 天 | 采集 + 脱敏 + lineage（`file`、`otel`、`langfuse` 三个采集器） | 100% 危险字段不落原始产物；≥1 名外部审查者复现 |
| **G2** | 第 30 天 | `collect → mint → run → gate` 闭环（含 `docker` 环境、`vigil.harness` 沙箱探针） | 同快照 10/10 通过；故意回归 1/1 被拦截 |
| **G3** | 第 60 天 | 3 个外部团队接入 + 协议冻结 | 3/3 完成导入，≥2/3 复现过一次失败 |
| **G4** | 第 90 天 | 生产失败转化 + judge 校准 | 生产选择集比随机样本多发现 ≥1 个真实回归 |

之后才是 `v0.2`（统计门禁、docker 环境、LLM judge + meta-eval）、`v1.0`（SLO 面板、flake 分类、conformance suite）。

**首轮明确不做**：通用 MCP 录制回放、跨组织公共错误签名库、语义去重、自研 model provider、完整可视化 UI、通用 MCP fuzzing、排行榜、自动 oracle 生成。

---

## 九、成功指标（不看 star）

1. **下游 CI 采用数**：多少个独立仓库在 CI 里跑 `vigil run`（唯一难刷的指标）。
2. **插件 owner 数**（比插件数重要，反映生态是否单点）。
3. **生产失败转化率**：线上失败变成可重跑回归的比例。
4. **被引用次数**：论文、厂商文档、RFP / 选型指南。
5. **可解释性**：阻断决策能否在一句话内说清原因。

---

## 十、隐私与合规红线

- 核心**零第三方依赖**，核心不做网络 I/O；一切外部接触都在插件里。
- 最小化默认拒绝：未知字段直接丢弃，已知字段内的 PII 打码并**逐条留痕**。
- 真实 secret 不写入用例；CI 中使用最小作用域 token。
- 贡献错误指纹只上报本地哈希，不上报原始 trace（v1alpha1 尚未启用任何上报）。

---

## 十一、参与贡献

请先读 [`AGENTS.md`](AGENTS.md)（给 AI coding 工具与贡献者的工程协议）与 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

- 协议变更 → 提 RFC（`RFC/0000-rfc-template.md`）
- 新插件类别 → 必须走 RFC + conformance
- 安全漏洞 → 见 [`SECURITY.md`](SECURITY.md)，请勿开公开 issue

## 许可

MIT，见 [`LICENSE`](LICENSE)。
