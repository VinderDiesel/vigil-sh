# RFC 0003: 外部插件包布局、环境能力契约与跨边界 Agent

- 状态：Accepted
- 作者：maintainers
- 创建日期：2026-09-19
- 影响范围：protocol, spec, conformance, docs, packages/

## 摘要

三项相互关联的协议级决策：

1. 需要外部 SDK / daemon 的插件一律放 `packages/` 下的**独立发行包**；
2. 环境插件必须声明 `capabilities`，由 `vigil.envbase.enforce` 统一判定拒绝（HARD-8）；
3. Agent 以**文件**形式穿越进程/容器边界，由 `vigil.harness` 在沙箱内执行。

## 动机

- 核心一旦吃进 `httpx` / `docker`，"pip install 就能跑"的早期传播杠杆就没了。
- 环境若按用例的 `side_effect_policy` 行事，用例 YAML 就成了提权通道。
- 远程环境无法接收活体 Python callable，需要有明确、可测的跨边界契约。

## 提案

### 1. 独立发行包

`packages/vigil-<group>-<name>/` 各自带 `pyproject.toml` 与 entry point。首批：
`vigil-collector-langfuse`（可选依赖 httpx，函数内延迟导入）、`vigil-env-docker`（shell 调 docker CLI）。
内置插件与第三方走同一注册机制，无特权路径。

### 2. 能力驱动的环境契约

| 请求 | 需要声明的能力 |
|---|---|
| `side_effect_policy=live` | `live-side-effects` |
| `side_effect_policy=mock`、`tool_mock_map` | `tool-mock` |
| `network_policy=open` | `open-network` |
| `network_policy=allowlist` | `allowlist-network` |
| `init_snapshot` | `snapshot` |

缺失即 `CapabilityError`。`clock_policy=frozen` 属于**建议性**能力（几乎没有沙箱能真正冻结时钟），
缺失只产生 warning 并写进运行报告，不阻断。

### 3. 跨边界 Agent

`vigil.harness.LoadedAgent` 同时携带 callable 与 path；远程环境读 `path` 并把文件挂进沙箱，
执行 `python -m vigil.harness --case ... --agent ...`，输出 RunResult JSON。
沙箱内崩溃一律落成 `ERROR`，绝不静默成 PASS。

## 影响分析

- 向后兼容：是（新增模块与包，未改既有字段语义）
- 受影响插件类别：environments（新增 capabilities 要求）、全部（harness 可选使用）
- 受影响 spec：新增 `spec/v1alpha1/environment.md`
- 新增 conformance：`assert_environment_contract`（能力声明 + 拒绝越权）、
  `assert_collector_contract` 复用至外部包

## 替代方案

- 环境自行 if-else 判断 → 每个插件一套逻辑，无法统一测试，已否决。
- 用 `pickle`/`cloudpickle` 传 callable → 反序列化即任意代码执行，已否决。
- 要求镜像内预装 vigil → 提高采用门槛；改为只读挂载源码 + `PYTHONPATH`。

## 未解决的问题

- `allowlist-network` 暂无可靠实现（容器内精确域名白名单需要代理/iptables），因此**不声明**，请求即拒绝。
- 文件级 fs 快照（非镜像级）未在 v1alpha1 支持。
- 多架构镜像与 registry 鉴权不在本 RFC 范围。

## 停止条件

若外部包的维护成本持续高于收益（连续两季度新增包 < 1 且 issue 无人响应），
将 `packages/` 降级为 `examples/` 中的参考实现，不再承诺 registry 兼容性。
