# RFC 0002: 插件三级维护与合规门禁

- 状态：Accepted
- 作者：maintainers
- 创建日期：2026-09-19
- 影响范围：protocol, conformance, docs

## 摘要

定义插件的三级维护制度（core / maintained / community），并规定 conformance 是上架 registry 的硬性门槛。

## 动机

生态的信任成本取决于"这个插件坏了谁修"。没有分级与门禁，用户踩坑的怨气会落在项目本身。

## 提案

| 级别 | 承诺 | 标记位置 |
|---|---|---|
| `core` | 项目维护，semver 保证 | README 插件表 + 包 metadata |
| `maintained` | 有具名 owner，best effort | 同上，附 owner |
| `community` | 无担保，明确标注 | 同上，加免责说明 |

合规要求（所有级别一致，无特权路径）：
1. 实现对应 Protocol，带 `name` / `version`。
2. 方法签名完整类型注解。
3. 禁止模块顶层 import 重型 SDK（HARD-4）。
4. 通过 `conformance/` 全部相关测试；内置插件与第三方插件同机制。

## 影响分析

- 向后兼容：是
- 受影响插件类别：全部
- 新增 conformance：SPI 结构检查、行为契约（幂等、不泄漏 PII、gate 不豁免硬阈值）

## 替代方案

- 只做代码 review 不做 conformance → 无法规模化，且依赖 maintainer 时间。
- 给内置插件豁免 → 内置插件一旦腐化，示范效应比第三方更糟。

## 未解决的问题

- registry 的托管形式（静态索引 vs 服务）尚未决定，取决于 G3 后的采用规模。
- owner 失联后的降级流程（maintained → community）需要自动化检测。

## 停止条件

若 conformance 维护成本高于插件收益（连续两季度新增插件 < 3），降级为"建议性测试"，registry 改为社区维护的索引。
