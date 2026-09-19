# Spec v1alpha1 — Environment

环境插件负责"把世界立起来，再拆掉"。它是 Vigil 里唯一被允许接触外部系统的组件，
因此它的契约重点是**能力声明与拒绝**，而不是功能多少。

## 1. SPI

```python
class EnvironmentProvider:
    name: str
    version: str
    capabilities: tuple[str, ...]

    def provision(self, contract: dict) -> EnvHandle: ...


class EnvHandle:
    def restore(self) -> str: ...  # 返回摘要；无法验证就 raise
    def execute(self, case, agent) -> RunResult: ...
    def teardown(self) -> None: ...
```

## 2. 能力表（`vigil.envbase`）

| 请求 | 必需能力 | 缺失时 |
|---|---|---|
| `side_effect_policy=live` | `live-side-effects` | 拒绝 |
| `side_effect_policy=mock` / `tool_mock_map` | `tool-mock` | 拒绝 |
| `network_policy=open` | `open-network` | 拒绝 |
| `network_policy=allowlist` | `allowlist-network` | 拒绝 |
| `init_snapshot` | `snapshot` | 拒绝 |
| `clock_policy=frozen` | `clock-freeze` | **仅 warning**（建议性） |

拒绝即 `CapabilityError`；runner 捕获后降级为 `UNDETERMINED` 并在报告里写明原因。
**用例 YAML 不得成为提权通道**（HARD-8）：判定只看环境声明的能力。

## 3. restore 的语义

`restore()` 必须返回可验证的世界摘要，或抛异常。
拿不到摘要的重跑只能叫 best-effort rerun，runner 会强制 `UNDETERMINED`。

`env_digest = snapshot_digest(image, init_snapshot, network_policy, allowlist,
tool_mock_map, seeds, clock_policy, side_effect_policy, env_vars)`。
世界不同的两次运行不得被当作同一实验比较。

## 4. 跨边界执行

远程环境（容器 / K8s / VM）不能接收活体 Python callable：

- Agent 以**文件**形式提供路径（`LoadedAgent.path`）；
- 沙箱内执行 `python -m vigil.harness --case ... --agent ...`，stdout 输出 RunResult JSON；
- case 与 agent 一律**只读挂载**——用例不得在沙箱内改写自己的 oracle。

## 5. v1alpha1 内置与首批外部环境

| 环境 | 位置 | 能力 |
|---|---|---|
| `noop` | core | 进程内执行，无网络、无快照、仅 dry-run |
| `docker` | `packages/vigil-env-docker` | 容器隔离、镜像级快照；`--read-only` + `--network none` 默认开启；`live` 需显式 opt-in |
