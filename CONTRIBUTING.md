# 贡献指南

## 开始之前

1. 读 [`AGENTS.md`](AGENTS.md)——硬约束（HARD-1 ~ HARD-12）与本文件的流程要求都出自那里。
2. 确认你的改动属于哪一档（AGENTS.md §4.2）：bug 修复 / 新插件 / 新插件类别 / 协议变更 / 文档。
3. **协议变更必须先提 RFC**，拿到一名 maintainer 同意后再动代码。

## 本地环境

```bash
git clone <your-fork>
cd vigil
pip install -e ".[dev]"
pytest && ruff check . && mypy
```

## 流程

```
issue（描述失败模式与复现） → RFC（若涉及协议） → 测试 → 实现 → 规范同步 → PR
```

- **先写测试**：conformance（若涉及 SPI）或 tests（行为）。
- **最小实现**：不要顺带重构无关代码，不要顺带加 UI / 数据库 / 异步。
- **同步规范**：改数据模型必须同步 `spec/v1alpha1/` 与 `conformance/`。

## 提交与 PR

- 提交信息：Conventional Commits（`feat:` / `fix:` / `docs:` / `refactor:` / `test:` / `chore:`）。
- PR 描述请回答 AGENTS.md §5 的 DoD 清单；缺项要显式说明。
- PR 需通过 CI（pytest + ruff + mypy + conformance）。

## 新插件

见 AGENTS.md §4.3。要点：实现 Protocol、完整类型注解、声明 entry point、补 conformance 测试、标注维护分级（core / maintained / community）。

**过不了 conformance 的插件不能进 registry，也不能被描述为"支持"。**

## 不在范围内（v1alpha1）

通用 MCP 录制回放、跨组织公共签名库、语义去重、统计门禁、自动 oracle 生成、自研 LLM judge、完整 UI、排行榜。详见 AGENTS.md §8。

## 行为准则

见 [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)。安全问题见 [`SECURITY.md`](SECURITY.md)。

## 许可

贡献即视为同意以 MIT 许可发布你的代码。
