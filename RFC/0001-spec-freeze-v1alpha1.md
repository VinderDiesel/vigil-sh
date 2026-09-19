# RFC 0001: 冻结 v1alpha1 规范（事件 / manifest / 门禁 / 分类法）

- 状态：Accepted
- 作者：maintainers
- 创建日期：2026-09-19
- 影响范围：spec, models, conformance

## 摘要

在决策门 G3 之前冻结四类规范的最小集合：`CanonicalEvent`、`CaseManifest`、`GateDecision`、`FAILURE_TAXONOMY`，并规定任何破坏性变更必须走 RFC + 主版本递增。

## 动机

插件生态能否活下来，取决于 hook 规范是否稳定（pytest 十年生命力的来源）。规范越早冻结，插件作者越敢投入；但同时，过早冻结会把错误设计固化。

## 提案

1. 冻结对象为**字段语义与必填性**，不冻结插件实现。
2. `spec_version` 强校验：未知版本直接报错，禁止静默兼容推断（HARD-2）。
3. 破坏性变更路径：新 RFC → 新 spec 版本 → 双写迁移期（≥1 个 minor）→ 旧版本弃用。
4. 每个被冻结对象必须在 `conformance/` 中有对应测试，测试缺失即视为未冻结。

## 影响分析

- 向后兼容：是（冻结期内）
- 受影响插件类别：全部六类
- 受影响 spec：`event.md`、`manifest.md`、`scoring.md`、`gate.md`
- 新增 conformance：未知 spec_version 报错、cluster_id 不参与身份判定、硬门禁不可豁免

## 替代方案

- 不冻结、快速迭代 → 插件作者无法投入，生态起不来。
- 冻结全部实现细节 → 过度僵化，违反 v0.x 阶段定位。

## 未解决的问题

- `max_slope`（长程衰减）在 v1alpha1 保留语义但不判定，是否应移出？
- 双写迁移期的具体长度取决于 G3 时的外部采用数。

## 停止条件

若 G3 未通过（少于 3 个外部团队接入），冻结范围收敛为"仅事件与 manifest"，其余降级为非规范建议。
