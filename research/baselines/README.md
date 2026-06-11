# 回测基线档案

## 规范

- **`current.json`** — 唯一权威基线。始终反映当前验证过的 ETF 池 + 各 preset 6y 指标。
- **`archive/`** — 历史基线。ETF 池变更时，旧 `current.json` 移入此处，文件名为 `<date>_<version>.json`。
- 基线不纳入日常 git commit（在 `.gitignore` 中），仅在发布时随版本一起提交。

## 使用方式

**查当前基线**：读 `current.json`。

**替换 ETF 前**：读 `current.json` 的 `preset<N>.tr_pct` 作为对比基准。

**替换 ETF 后验证通过**：
1. `cp current.json archive/2026-06-10_v3.6.0.json`
2. 更新 `current.json` 为新池 + 新指标
3. 随版本发布 commit

**替换 ETF 后验证失败（回退）**：不做任何操作，`current.json` 保持不变。
