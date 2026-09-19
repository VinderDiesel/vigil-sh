# vigil-env-docker

Vigil environment plugin：在容器里跑用例。**Tier: maintained.**

## 安装与前提

```bash
pip install vigil-env-docker
```

需要可用的 Docker daemon（本包 shell 调用 `docker` CLI，**不依赖** Python docker SDK，
因此不会把重型依赖带进 `vigil` 核心，HARD-1 / HARD-4）。

## 用法

```bash
vigil run --cases examples/case.json \
          --agent examples/agent.py \
          --env docker \
          --scorer exact \
          --junit out.xml --json out.json
```

在 `CaseManifest.env` 中声明：

```json
{
  "image": "python:3.11-slim",
  "network_policy": "none",
  "side_effect_policy": "dry-run",
  "init_snapshot": "my-registry/app:sha-abc",
  "timeout_s": 120
}
```

## 隔离默认值

| 契约字段 | 默认 | 容器实现 |
|---|---|---|
| `network_policy: none` | ✅ 默认 | `--network none` |
| `network_policy: open` | 需声明 | `--network bridge` |
| `side_effect_policy: dry-run` | ✅ 默认 | `--read-only` |
| `side_effect_policy: live` | **默认拒绝** | 需 `DockerEnvironment(allow_live=True)` |
| 提权 | 禁止 | `--security-opt no-new-privileges`、`--pids-limit 256` |
| 挂载 | 只读 | case/agent/pkg 均 `:ro` |

能力由 `vigil.envbase.enforce` 判定：**用例 YAML 无法自我提权**（HARD-8）。
`allowlist-network` 未声明 → 请求 allowlist 直接拒绝（我们无法在容器内可靠实现精确域名白名单，
与其假装，不如拒绝）。

## 执行机制

容器内运行的是核心自带的探针：

```
python -m vigil.harness --case /vigil/case/case.json --agent /vigil/case/agent.py
```

`vigil` 源码以只读方式挂载（不要求在镜像里安装 vigil）；Agent 以**文件**形式穿越边界——
活体 Python callable 无法序列化进容器，因此 `--agent` 必须给路径。

## 重放语义

`restore()` 校验镜像存在并返回 `image_id + contract` 的摘要；拿不到就抛错，
runner 会把结果降级为 `UNDETERMINED`，**不会给 PASS**。
`init_snapshot` 支持镜像 tag/digest（文件级 fs 快照不在 v1alpha1 范围）。

`clock_policy=frozen` 属于**建议性**能力：容器不保证冻结时钟，缺口会在运行报告的 warning 里显式列出。

## 测试

```bash
pytest                       # 纯逻辑（不需要 daemon）
pytest -m integration        # 需要 daemon，缺失时自动 skip
```

## 许可

MIT。
