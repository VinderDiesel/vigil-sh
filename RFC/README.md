# RFC 流程

**任何**以下变更必须先有 RFC，公开讨论并编号归档：

- 新增插件类别
- 修改 `src/vigil/protocol.py` 中的 SPI
- 修改数据模型字段语义（`models/`）
- 修改门禁语义或 SLO 判定规则
- 修改失败分类法
- 改变隐私/最小化边界（如 `DEFAULT_KEEP` 白名单）

流程：复制 `0000-rfc-template.md` → 提 PR → 至少 1 名 maintainer 同意 → 合并（状态 Draft）→ 实现 → 状态转 Accepted。

RFC 不替代 issue；bug 修复与文档改动不需要 RFC。
