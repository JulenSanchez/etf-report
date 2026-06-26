# params/ — 参数优化证据

> 本目录记录参数优化报告和证据，不维护当前生效参数。当前生效值以 `../../config/quant_universe.yaml` 为准；参数映射契约见 `../../src/etf_report/core/quant_contract.py`。

## 当前执行流程

参数优化统一按：

```text
../../docs/runbook/v2-quant/optimization.md
```

执行。旧目录中的早期阶段划分和旧 preset 命名均为历史记录，不作为当前流程。

## Latest Evidence Reports

| 目录 | 内容 | 状态 |
|---|---|---|
| `gam-3-20260623/` | gam-3 参数优化 | 最新证据，是否 promotion 需走 promotion runbook |
| `gam-1-20260622-v2/` | gam-1 修复后优化报告 | 证据，需确认 analyzer 口径 |
| `gam-2-20260622/` | gam-2 优化报告 | 证据，需确认 analyzer 口径 |
| `gam-1-20260618/` | gam-1 v3.8 后优化记录 | 历史证据 |
| `act-1-20260617/` | act-1 参数优化 | 历史证据 |
| `zen-1-20260617/` | zen-1 参数优化 | 历史证据 |
| `gam-2-20260617/` | gam-2 参数优化 | 历史证据 |

## Historical Snapshots

早期参数研究曾使用旧 preset 命名。它们只代表当时实验上下文，不代表当前配置。

当前命名以 `../../config/quant_universe.yaml` 中的 `act-*` / `zen-*` / `gam-*` 为准。

## 已废弃或不再推荐复用的旧方法

以下内容不再作为当前研究入口：

- F2 / F4 / F5 / F6 相关旧扫描。
- 旧 preset 命名相关报告。
- 单因子粗扫 → 交叉 → 随机收尾的旧方法论。

如需重新研究，按 `../../docs/runbook/v2-quant/optimization.md` 重跑，不复用旧结论。
