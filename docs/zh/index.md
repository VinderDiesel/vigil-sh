# Vigil（衡鉴）

**把 Agent 的一次执行，变成可重放、可评分、可进 CI 门禁的可靠性资产。**

Vigil 不是追踪平台，不是基准榜单，也不是又一个 LLM 评测框架。它是连接"生产证据"和
"工程门禁"的那一层：吃现有可观测平台的导出，产出版本化的回归用例，用受控环境重放，
用多评分器判定，最后在 CI 里给出可执行的放行/阻断决策。

!!! warning "状态"
    v0.1.0-alpha，规范版本 `v1alpha1`。协议未冻结，勿用于关键生产决策。

## 核心链路

```
  Execution          CanonicalEvent         CaseManifest          Score            GateArtifact
 (任意来源)    →    (规范化+脱敏)     →    (版本化契约)    →   (评分+弃权)   →   (JUnit/JSON)
       ▲                                        │
       └────────────  replay ────────────────────┘
```

## 文档

- [架构](architecture.md) — 分层、依赖方向、插件体系的设计理由
- [可靠性手册](reliability-handbook.md) — 方法论：弃权、分歧、重放模式与措辞纪律
- [路线图](roadmap.md) — 决策门 G1–G4 与范围收缩条件

工程协议（给贡献者与编码 Agent）见仓库根目录
[AGENTS.md](https://github.com/VinderDiesel/vigil-sh/blob/main/AGENTS.md)，
规范文本见 [spec/v1alpha1](https://github.com/VinderDiesel/vigil-sh/tree/main/spec/v1alpha1)。

## 快速开始

```bash
pip install vigil-sh           # 发行版
vigil plugins                  # 查看已注册插件
```

端到端样例（采集 → 造用例 → 跑套件 → 门禁，约 5 分钟，无需 Docker / 云 / 模型 Key）
见仓库 [`examples/minimal-agent/`](https://github.com/VinderDiesel/vigil-sh/tree/main/examples/minimal-agent)。
