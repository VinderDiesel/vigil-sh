# 外部插件包（independent distributions）

这里的每个包都是**独立发行包**，不在 `vigil` 核心里。原因只有两条（AGENTS.md HARD-1 / HARD-4）：

1. 核心必须零第三方依赖，`pip install vigil` 就能跑；
2. 重型 SDK（`httpx`、`docker`…）永远不进核心，且**不在模块顶层 import**。

| 包 | 插件类别 | 注册名 | Tier | 外部依赖 |
|---|---|---|---|---|
| [`vigil-collector-langfuse`](vigil-collector-langfuse/) | collectors | `langfuse` | maintained | httpx（可选，仅 API 模式，函数内延迟导入） |
| [`vigil-env-docker`](vigil-env-docker/) | environments | `docker` | maintained | Docker daemon（shell 调 CLI，不用 SDK） |

安装：

```bash
pip install vigil                        # 核心：file / otel 采集器、noop 环境
pip install vigil-collector-langfuse     # + langfuse 采集
pip install vigil-env-docker             # + 容器环境
vigil plugins                            # 已注册插件一览
```

## 新增一个外部包

```bash
python scripts/new_plugin.py --group environments --name k8s --class K8sEnvironment
```

然后：

1. 把生成目录移到 `packages/vigil-<group>-<name>/`；
2. 补 `pyproject.toml`（独立 version、独立 entry point、标注 tier）；
3. 测试里复用核心的合规断言：
   ```python
   from vigil.conformance import assert_environment_contract


   def test_conformance():
       assert_environment_contract(K8sEnvironment)
   ```
4. README 里写清**外部依赖、能力声明、以及不承诺什么**。

## 规则（对所有外部包一致，内置插件无特权路径）

- 声明 `capabilities`（环境类）与 `name`/`version`（所有类别）；
- 方法签名完整类型注解；
- 重型依赖只在函数内部 import；
- 跑 `vigil.conformance` 的对应断言，过不了就不能进 registry，也不能在文档里写成"支持"。
