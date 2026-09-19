# AGENTS.md — Vigil 工程协议（给 AI coding 工具与贡献者）

> 本文件是**给编码 Agent 和贡献者读的**，不是产品说明（那是 `README.md`）。
> 目标：让任何 Agent（人类也一样）在不追问的情况下，能安全、一致地改动这个仓库。
>
> **读完后你应当能回答三个问题**：什么绝对不能碰？改动的正确顺序是什么？怎样算做完？

---

## 0. 三十秒摘要

Vigil 把 Agent 执行转成可靠性资产，链路是：

```
Execution → CanonicalEvent → CaseManifest → Score → GateArtifact
```

本项目**技术难度不在算法，在纪律**：清洗 trace、维护契约、追兼容性、写 conformance 测试，全是脏活。因此本文件 80% 是约束，不是指南。

**如果你只记一条**：不确定时，**缩小范围 + 显式报 UNDETERMINED**，永远优于"扩展功能 + 输出一个乐观结论"。

---

## 1. 仓库地图

```
vigil/
├── src/vigil/
│   ├── protocol.py        # 六类插件 SPI —— 宪法，只能经 RFC 修改
│   ├── cas.py             # 内容寻址：raw_hash / canonical_hash / cluster_id
│   ├── registry.py        # entry points 插件发现
│   ├── runner.py          # 编排：env → 执行 → 评分 → 聚合 → 决策
│   ├── artifacts.py       # JUnit XML / JSON / PR 评论产物
│   ├── cli.py             # 唯一用户入口（stdlib argparse，禁止重型 CLI 框架）
│   ├── models/            # event / case / result / gate 数据模型（零依赖）
│   └── plugins/           # 内置插件，与第三方插件走同一注册路径
├── spec/v1alpha1/         # 规范文本：事件、manifest、environment、scoring、gate
├── conformance/           # 插件 SPI 合规测试 —— 生态生命线，CI 必跑
├── tests/                 # 单元测试
├── packages/              # 独立发行包（需要外部 SDK / daemon 的插件）
│   ├── vigil-collector-langfuse/   # httpx 延迟导入，仅 API 模式需要
│   └── vigil-env-docker/           # shell 调 docker CLI，需 daemon
├── examples/
│   ├── minimal-agent/     # 端到端可跑的最小样例（agent.py + cases/ + trace.jsonl）
│   └── otel-export/       # OTLP JSON 样例
├── docs/                  # 方法论与架构说明
├── RFC/                   # 协议级变更提案（必须编号归档）
└── pyproject.toml         # 依赖 + entry points 声明
```

**核心 vs 外部包的判定**：需要 `httpx` / `docker` / `k8s` / 任何 SDK 或外部 daemon 的插件，
一律放 `packages/` 下的独立发行包，核心保持 `pip install vigil` 即可跑。

**依赖方向（单向，不得逆行）**：

```
collector → minimizer → selector → environment → scorer → gate
```

- 所有插件可 import：`vigil.models.*`、`vigil.cas`
- 插件**禁止** import 另一个插件的实现（跨层需求走 manifest）
- 插件**禁止** import 第三方 SDK 到模块顶层（见 HARD-4）

---

## 2. 硬约束（HARD RULES）— 违反即 PR 拒绝

编号引用，例如："这条改动违反 HARD-3"。

| # | 约束 | 为什么 |
|---|---|---|
| **HARD-1** | `src/vigil/core` 与 `models/` **零第三方依赖**（含运行期与 import 期）。CLI 用 stdlib `argparse`。 | 个人开发者 `pip install` 就能跑起来，是早期传播的唯一杠杆 |
| **HARD-2** | `spec_version` 必填且必须被校验；未知版本**直接报错**，不兼容推断。 | 静默 schema 漂移是评测系统最难查的 bug |
| **HARD-3** | 三种哈希**永不混用**：`raw_hash`（原始字节）/ `canonical_hash`（规范化后）/ `cluster_id`（语义簇，仅建议）。禁止用 `cluster_id` 去重或做身份判断。 | 语义去重会删掉最稀有的失败——而那正是用例集的全部价值 |
| **HARD-4** | 插件**禁止**在模块顶层 import `docker` / `kubernetes` / `requests` / `httpx` / `boto3` 等；需要就放进 `packages/` 下的独立发行包，且只在函数内部延迟导入。 | 有 conformance 测试强制检查（`test_core_imports_no_heavy_sdk`；外部包另有"模块导入不含 httpx"的测试） |
| **HARD-13** | 环境插件必须声明非空 `capabilities`，并由 `vigil.envbase.enforce` 判定；**禁止**读取用例的 `side_effect_policy` 来决定放行（HARD-8 的执行形式）。 | 用例 YAML 不得成为提权通道；统一判定才能被 conformance 覆盖 |
| **HARD-14** | Agent 以**文件**穿越进程/容器边界：远程环境只能读 `LoadedAgent.path` 并用 `vigil.harness` 在沙箱内执行。禁止 pickle / cloudpickle / 序列化活体 callable。 | 反序列化即任意代码执行 |
| **HARD-15** | 远程环境的挂载一律 `:ro`，且崩溃的沙箱执行必须落成 `ERROR`，不得静默成 PASS。 | 用例不得在沙箱内改写自己的 oracle |
| **HARD-5** | Judge 可以**弃权**。禁止把 `None` / 低置信度 / 无 oracle 强行转成 `0.0` 分，禁止对分歧静默取均值。 | "LLM-as-Judge 漂移了没人知道"是本项目的头号公敌 |
| **HARD-6** | 环境未验证（`restore()` 未返回 digest）⇒ 结果强制 `UNDETERMINED`。禁止在无验证环境下产出 `PASS`。 | 无验证的 PASS 比 FAIL 有害得多 |
| **HARD-7** | 硬门禁（安全 / PII / 策略违规 / 不可逆副作用）**永不豁免**：不参与统计检验、不设置信区间、不允许 `--waive`。 | 安全阈值被统计豁免，等于没有阈值 |
| **HARD-8** | 环境按**自己的 contract** 拒绝请求，不读用例里的 `side_effect_policy` 来自我提权。 | 用例 YAML 不得成为提权通道 |
| **HARD-9** | 最小化**默认拒绝**：未知字段丢弃；已知字段名含 secret 提示 ⇒ 整字段打码；每条移除都要留痕进 `redactions`。 | 一条带客户邮箱的用例进了公开 CI 日志，就是这个项目的终结 |
| **HARD-10** | 不写"任意 Agent / 任意执行 / 完全确定性重放"这类措辞。用例必须声明 `replay_mode`，只允许 `mock-replay`、`snapshot-replay`、`sandbox-execute` 说自己可重放。 | 过度承诺被证伪一次，信任归零 |
| **HARD-11** | 禁止在 v1alpha1 引入统计门禁（bootstrap / McNemar / 序贯检验）的半成品实现。 | 没有声明最小可检测效应的门禁，会训练团队反复重跑 CI |
| **HARD-12** | 数据模型改动必须同步 `spec/v1alpha1/*.md` + `conformance/`，三者不一致视为未完成。 | 规范、实现、合规测试是同一件事的三种表述 |

---

## 3. 词汇表（措辞纪律）

| ❌ 禁止写法 | ✅ 正确写法 |
|---|---|
| "任何 Agent 都能接入" | "已适配 X、Y 两个框架（见兼容矩阵）" |
| "确定性重放" | "`mock-replay` 模式下重放"（须带模式名） |
| "评分通过" | "两个 scorer 一致判 PASS，分歧度 0.0" |
| "失败率下降" | "在 N 次重复下 pass_rate 由 0.82 升至 0.88，flake_rate 0.01" |
| "用例已生成" | "用例已生成，oracle 未评审，confidence=0.3" |
| "支持所有环境" | "`noop` 环境仅支持进程内执行，无快照能力" |

**任何对外可见的结论，必须携带其成立条件。** 写不出条件，就把结论降级为"未验证假设"。

---

## 4. 标准开发流程（SOP）

### 4.1 改动的正确顺序

```
1. 判类        这是 (a) bug 修复 / (b) 插件 / (c) 协议变更 / (d) 文档？
2. (c) 必须先写 RFC → RFC/000N-*.md，获得至少 1 名 maintainer 同意后才能动代码
3. 先写测试     conformance/（若涉及 SPI）或 tests/（行为）
4. 再写实现     最小实现，不加"顺手也做一下"的东西
5. 同步规范     spec/v1alpha1/ 与 docs/
6. 自检         ruff + mypy(strict) + pytest，见第 6 节命令
7. 提交         Conventional Commits，PR 描述回答第 5 节 DoD 清单
```

**顺序不可颠倒。** 第 3 步之前先写实现，是本项目最常见的 PR 被拒原因。

### 4.2 变更分类速查

| 变更 | 需要 RFC | 需要 conformance | 需要 spec 更新 |
|---|:--:|:--:|:--:|
| 修 bug / 改文案 | 否 | 否 | 否 |
| 新增插件（已有类别，核心内） | 否 | **是** | 否 |
| 新增插件（已有类别，外部包） | 否 | **是**（复用 `vigil.conformance`） | 仅当改环境能力语义 |
| 新增插件**类别** | **是** | **是** | **是** |
| 改数据模型字段 | **是** | **是** | **是** |
| 改环境能力表（`envbase.REQUIRED_CAPABILITIES`） | **是** | **是** | **是** |
| 改门禁语义 | **是** | **是** | **是** |
| 新增 CLI 子命令 | 否 | 否 | 视情况 |

### 4.3 新增插件 SOP

0. **先判定位置**：需要外部 SDK / daemon ⇒ `packages/vigil-<group>-<name>/`（独立发行包）；
   纯 stdlib ⇒ `src/vigil/plugins/`。
1. 复制 `src/vigil/plugins/` 中同类实现作为模板（或用 `python scripts/new_plugin.py` 生成骨架）。
2. 实现对应 Protocol（`src/vigil/protocol.py`），**必须**带 `name` / `version` 类属性。
3. 方法参数与返回**必须**完整类型注解（conformance 会检查）。
4. 在 `pyproject.toml` 声明 entry point；内置插件与第三方**同一机制**，无特权路径。
5. 在 `conformance/test_plugin_spi.py` 增加该插件的行为契约测试。
6. 测试里复用核心的合规断言（`from vigil.conformance import assert_*_contract`），
   不要另写一套——生态的一致性靠共享断言维持。
7. 在 README 插件表标注维护分级（core / maintained / community），
   并写清外部依赖与"不承诺什么"。

---

## 5. 定义完成（DoD）清单

提交 PR 前逐条自查，缺一项就在 PR 描述里显式说明原因：

- [ ] `pytest` 全绿（含 `conformance/`）
- [ ] `ruff check` 无告警；`mypy`（strict）通过
- [ ] 新增/修改的行为**至少 1 个测试**，且该测试在改动前是失败的
- [ ] 涉及 SPI ⇒ conformance 已扩展
- [ ] 涉及数据模型 ⇒ `spec/v1alpha1/` 已同步
- [ ] 无新增第三方依赖进入核心（HARD-1）
- [ ] 无新的"过度承诺"措辞进入 README / CLI 输出（HARD-10、第 3 节）
- [ ] 错误信息可被用户理解（不说 "assertion failed"，要说清哪个字段、期望什么）
- [ ] 失败路径有显式状态（ERROR / UNDETERMINED / abstain），没有静默兜底

---

## 6. 命令速查

```bash
pip install -e ".[dev]"
pip install -e "packages/vigil-collector-langfuse" -e "packages/vigil-env-docker"

pytest                      # 单元 + conformance（核心，含已安装的外部包）
pytest conformance -m conformance
make test-packages          # 外部包各自的测试（docker 集成测试无 daemon 时自动 skip）
ruff check . && ruff format --check .
mypy                        # strict，配置见 pyproject.toml

vigil plugins                                   # 列出已注册插件
vigil collect <file.jsonl> --out collected.json # 采集 + 最小化（默认 file 采集器）
vigil collect <otlp.json>  --collector otel     # OTel / GenAI semconv
vigil collect <export.json> --collector langfuse
vigil collect "langfuse://<host>" --collector langfuse --options '{"since":"2026-09-01"}'  # API 模式
vigil select  <file.jsonl> --options '{...}'
vigil mint --case-id X --input '{...}' --oracle '{...}' --out case.json
vigil run --cases <dir|file> --agent <agent.py> \
          [--env noop|docker] [--scorer exact] [--repeats 3] \
          [--slo slos.json] [--junit out.xml] [--json out.json] [--comment pr.md]
vigil gate  --report out.json [--slo slos.json]   # 不改代码重跑门禁策略
vigil explain --cases <dir> [--case-id X]        # 打印用例与其允许的措辞
```

退出码：`0 = allow`，`1 = block`。CI 依赖退出码，不要改成抛异常。

---

## 7. 代码规范

- Python ≥ 3.11 目标；类型注解**必须完整**（`mypy --strict`）。
- `from __future__ import annotations` 是每个模块的第一行。
- 行长 ≤ 100；`ruff` 规则集：`E,F,I,UP,B,SIM`。
- 数据模型用 `@dataclass`，带 `to_dict()` / `from_dict()`，且不引入序列化库。
- 异常处理原则：**降级而非崩溃**（环境/评分器失败 → warning + UNDETERMINED），但**契约违反要报错**（未知 `spec_version`、缺字段）。
- 注释写"为什么"，不写"做了什么"。每条 HARD 约束在代码里都有对应注释指向本文件。
- 提交信息：Conventional Commits（`feat:` / `fix:` / `docs:` / `refactor:` / `test:` / `chore:`），协议变更附注 `RFC-000N`。

---

## 8. 明确不做（v1alpha1 范围外）

**Agent 遇到以下需求时，应回复"这在 v1alpha1 范围内之外，需要先过 RFC / 决策门 G3"，而不是直接实现：**

- 通用 MCP 录制 / 回放（含 web、浏览器状态、外部 API 幂等）
- k8s / VM / 浏览器环境（docker 之后按需，须复用 `envbase` + `harness` 契约）
- 跨组织公共错误签名库 / 排行榜 / 网络效应型数据共享
- 语义去重与聚类（HARD-3）
- 统计门禁（bootstrap / McNemar / 序贯检验）（HARD-11）
- 自动 oracle 生成（用例必须人工确认，见 `vigil mint --oracle`）
- 自研 model provider / 自研 LLM judge（先复用 DeepEval、Braintrust、Promptfoo）
- 完整可视化 UI / Dashboard（输出 JUnit + JSON + PR 评论即可）
- "支持任何 Agent 框架"的自动适配层

理由一致：这些都以"最小闭环已被证明"为前提。在 G2 之前实现它们，会同时扩大状态空间、维护面与合规责任。

---

## 9. AI Agent 在此仓库的常见失败模式

| 失败模式 | 正确做法 |
|---|---|
| 为了"更完整"顺手加 UI、加数据库、加异步 | 先跑 `pytest`，只做 issue 要求的最小改动 |
| 把 `None` 评分当成 0 分处理（"方便统计"） | 保留弃权，标记 `needs_review`（HARD-5） |
| 用 `cluster_id` 去重"清理"用例集 | 只在人工复核后合并（HARD-3） |
| 给核心加 `pydantic` / `typer` / `docker` 依赖 | 需要能力就做成插件包（HARD-1、HARD-4） |
| 改了数据模型但没改 spec 与 conformance | 三者同时改（HARD-12） |
| 为了让 CI 变绿而放宽阈值或加 `--waive` | 先定位 flake 根因；硬门禁永不豁免（HARD-7） |
| 输出"已完成 X"却没有可运行验证 | 必须给出命令与实际输出 |
| 生成"任意 Agent 可重放"类文案 | 按第 3 节改写（HARD-10） |

---

## 10. 决策门与止损（写进机制，不是写进希望）

| 门 | 时间 | 未通过则 |
|---|---|---|
| G1 | 第 14 天 | 停止建 UI 与签名库，转向 collector-only |
| G2 | 第 30 天 | 砍掉 MCP proxy，仅保留 `record-only` |
| G3 | 第 60 天 | 协议收敛到 v1alpha1，暂停跨框架自动发现 |
| G4 | 第 90 天 | 停止"可靠性平台"叙事，转向评测数据治理 |

追加的停止条件：**任何一次合规审计发现 PII / secret 泄漏 ⇒ 立即冻结采集与导出，只保留本地最小化模式。**

---

## 11. 安全红线（无需讨论，直接拒绝）

- 禁止把真实 secret、token、客户 PII 写入用例、日志、JUnit 产物或 issue。
- 禁止在 conformance / 测试中发起真实网络请求或调用真实付费 API。
- 禁止放宽 `minimizer_default.py` 的 `DEFAULT_KEEP` 白名单（属 RFC 级变更，因为它改变所有用例的隐私边界）。
- 禁止实现绕过硬门禁的开关。

发现泄漏：按 `SECURITY.md` 私下报告，不开公开 issue。

---

## 12. 改文件前先看这里

| 你想改的东西 | 先读 |
|---|---|
| 新增外部包 | `packages/README.md` + RFC 0003 |
| 环境能力 / 拒绝逻辑 | `src/vigil/envbase.py` + `spec/v1alpha1/environment.md` |
| 沙箱内执行探针 | `src/vigil/harness.py` + `spec/v1alpha1/environment.md` §4 |
| 插件接口 | `src/vigil/protocol.py` + `spec/v1alpha1/` |
| 用例字段 | `src/vigil/models/case.py` + `spec/v1alpha1/manifest.md` |
| 评分与弃权 | `src/vigil/models/result.py` + `spec/v1alpha1/scoring.md` |
| 门禁语义 | `src/vigil/models/gate.py` + `spec/v1alpha1/gate.md` |
| 编排流程 | `src/vigil/runner.py` |
| 失败分类 | `src/vigil/models/gate.py::FAILURE_TAXONOMY` + `spec/v1alpha1/taxonomy.md` |
| 端到端行为 | `examples/minimal-agent/`（先跑通它） |

**最后一句**：这个项目的壁垒不是代码，是纪律。写 conformance、维护契约、拒绝过度承诺——看似慢，恰恰是它不会被下一版模型抹掉的原因。
