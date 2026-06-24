# 研究投产 Promotion 流程

> **触发词**: 用户说“promotion”“采纳研究结果”“写入生产 preset”。本文定义 research 结论进入 production 的唯一门禁。

## 定位

promotion 是 research → production 的移交流程。它不是普通研究记录，也不是发布流程。

```text
research report → promotion 判断 → config / docs / payload 变更 → release.md 发布
```

## 输入

- 研究报告：`research/params/<run>/report.md`、`research/pool/rounds/*.md` 或其它研究证据。
- 当前生产事实源：`config/quant_universe.yaml`。
- 当前状态：`plans/Board.md`。

## 必备判断

promotion 前必须回答：

1. 研究结论是否基于当前代码和当前数据？
2. 是否和当前生产 preset / universe 对比？
3. 是否覆盖必要窗口：1Y / 3Y / 6Y 或需求明确的替代窗口？
4. 是否存在退化？退化是否符合该主体哲学和约束？
5. 是否需要开 REQ？凡涉及 config、UI、payload、正式页展示的变更都必须有 REQ。

## 结果类型

只允许三类结论：

```text
reject
research-only
promote-with-guardrails
```

- `reject`：结论不采纳，记录原因。
- `research-only`：保留研究价值，但不写入生产。
- `promote-with-guardrails`：允许进入 config / Tuner / 正式页，但必须写清边界和回退条件。

## 退化规则

“有退化不阻塞升级”只适用于继续研究或生成候选，不适用于直接生产 promotion。

生产 promotion 必须满足：

- 核心目标不低于当前生产配置；或
- 退化被明确接受，且换来更高优先级的目标，并由用户确认。

## Promotion Ledger

所有 promotion 必须登记到：

```text
research/promoted/README.md
```

每条记录至少包含：

```text
date
title
source
req
landed_in
status: active | rolled_back | superseded | draft
superseded_by
```

详细记录可以放在 `research/promoted/records/`，但必须由 ledger 索引。

## 落地范围

按变更类型更新：

| 类型 | 可能落地位置 |
|---|---|
| preset 参数 | `config/quant_universe.yaml` |
| Tuner 控件/解释 | `templates/tuner.html`、`src/etf_report/core/quant_contract.py` |
| 正式页展示 | `assets/js/quant-main.js`、payload helper |
| ETF 池 | `config/quant_universe.yaml`、`research/pool/README.md` |
| 文档 | `docs/design/`、`docs/runbook/` |

## 最小验证

按变更选择：

```bash
python -m pytest tests/test_quant_contract.py -q
python -m pytest tests/test_quant_* -q
python scripts/quant_build_payload.py
python scripts/quant_backtest.py --preset <preset> --start 2023-01-01
```

发布、提交、push、stable 更新不在本文执行，统一进入 `docs/runbook/release.md` 和 `docs/runbook/stable.md`。
