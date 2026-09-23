# Changelog

本文件遵循 Keep a Changelog 格式；本项目采用 SemVer（0.x 阶段：minor 可含破坏性变更）。

## [Unreleased 0.2.0] - G1/G2 基础设施

### 新增
- **采集器 `otel`**（core）：OTLP JSON → `CanonicalEvent`，含 GenAI semconv 映射
  （`gen_ai.*` → `model` / `tool` / `arguments` / `usage`），启发式 `effect_class` 分类，
  未识别一律 `unknown`。原始工具返回默认不携带（PII 密集）。
- **采集器 `langfuse`**（独立包 `vigil-collector-langfuse`）：支持导出文件与
  `langfuse://` API 模式；默认只产出 `input`/`output` 的 SHA-256 摘要，原文需 `include_io=true`；
  `httpx` 仅在函数内延迟导入。
- **环境 `docker`**（独立包 `vigil-env-docker`）：`--read-only` + `--network none` 默认开启，
  `no-new-privileges`、pid/内存/CPU 限制；`live` 副作用需显式 `allow_live=True`；
  `allowlist-network` 未声明即拒绝；shell 调 `docker` CLI，不引入 Python SDK。
- **`vigil.envbase`**：环境能力契约（`REQUIRED_CAPABILITIES` / `enforce` / `advisory_warnings` /
  `snapshot_digest`），统一判定拒绝与建议性告警。
- **`vigil.harness`**：沙箱内执行探针（`python -m vigil.harness`），支持 `LoadedAgent`
  以文件形式穿越进程/容器边界；崩溃一律落成 `ERROR`。
- **`vigil.conformance`**：合规断言从测试文件提升为公共 API，外部包可直接复用
  （`assert_collector_contract` / `assert_environment_contract` / `check_plugin` …）。
- 最小化：`token` 计数类字段不再被误判为 secret（`NOT_SECRET_PATTERN`）。
- 文档双语化：默认 `README.md` 改为英文版，中文版移至 `README_zh.md`，顶部互设语言跳转。
- 文档站双语：mkdocs 站点英文为默认（站点根路径），中文移入 `/zh/`，头部语言下拉切换；
  无第三方 i18n 插件依赖（Community 版 material 不含该插件，采用双导航树方案）。
- RFC 0003（外部包布局 / 环境能力契约 / 跨边界 Agent）、`spec/v1alpha1/environment.md`。

### 变更
- **发行包改名 `vigil` → `vigil-sh`**（PyPI 上 `vigil` 名字已被占用）。Python import 名与 CLI 命令名
  保持 `vigil` 不变；外部插件包名（`vigil-collector-*` / `vigil-env-*`）不受影响。
- 环境插件必须声明 `capabilities`（HARD-13）；`noop` 改为能力驱动拒绝。
- `clock_policy=frozen` 从"必需能力"降级为建议性告警（几乎没有沙箱能真正冻结时钟）。
- runner 支持 `--agent` 传文件路径（远程环境需要）。

### 修复
- `pass_at_k` 此前只统计"多次运行结果有分歧"的用例，稳定通过的用例被计为 0（`repeats=1` 时恒为 0）。
  现定义为"前 k 次运行中至少一次 PASS 的用例占比"（k = 1..最大重复次数），定义同步至 `spec/v1alpha1/gate.md`。
- `expires_at` 此前仅空字符串被视为过期，真实日期不生效，且过期只产生 warning、结果仍可门禁。
  现按 ISO 8601 日期与当天比较（当日仍有效），无法解析的取值一律按过期处理（保守降级）；
  过期用例结果强制 `UNDETERMINED`，但 `policy_violation` 等安全信号不受影响（HARD-7）。
  字段语义同步至 `spec/v1alpha1/manifest.md`。

## [0.1.0] - 2026-09-19 (alpha)

规范版本：`v1alpha1`（未冻结）。

### 新增
- 核心链路 `collect → select → mint → run → gate`，CLI 全部基于 stdlib（零第三方依赖）。
- `CanonicalEvent` / `CaseManifest` / `RunResult` / `GateDecision` 数据模型，含 `spec_version` 强校验。
- 内容寻址：`raw_hash` / `canonical_hash` / `cluster_id` 三层标识分离。
- 内置插件：collector `file`、minimizer `default`、selector `rules`、environment `noop`、scorer `exact`/`contains`、gate `hard`。
- 五种重放模式与措辞约束；环境未验证时结果强制 `UNDETERMINED`。
- Judge 弃权与分歧度；`needs_review` 标记。
- CI 产物：JUnit XML、JSON 报告、PR 评论 Markdown。
- conformance 合规测试集（插件 SPI + 行为契约，含 PII 泄漏检查）。
- 失败分类法 v1alpha1（8 类，含 `oracle_ambiguous`）。
- `examples/minimal-agent` 端到端可跑样例。

### 未包含（有意为之）
- 统计门禁（bootstrap / McNemar / 序贯检验）——需先声明最小可检测效应。
- 语义去重、跨组织公共错误签名库、通用 MCP 录制回放、自动 oracle 生成、完整 UI。
- LLM judge 与 `audit-judge`（meta-eval）——计划于 v0.2，需独立标注集。
