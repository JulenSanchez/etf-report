# 预设投产与迭代

> **触发词**: 用户说"preset-change""采纳研究结果""写入生产 preset""切换默认"。本文定义 preset 从研究到生产、从生产到默认的完整门禁。

**关联文档**: 量化运维 → `docs/runbook/v2-quant/overview.md` | 参数优化 → `docs/runbook/v2-quant/optimization.md` | 发布 → `docs/runbook/release.md`

## 流程总览

```
研究                      裁决                    极端分析(杠杆)           落地                    收口
─────                    ────                    ────────────             ────                    ────
optimization report      → 必备判断 → 结论分类   → extreme_analyzer.py    → 更新 config/Tuner     → 登记 ledger
                          → reject / research-only / adopt-with-guardrails  → 通过后继续             → 可选: 切换默认
                                                                           → 发布按 release.md
```

| 变更规模 | 追踪方式 |
|---------|---------|
| 新 preset 或覆盖现有 preset | 开 `plans/REQ-XXX.md` 记录裁决和证据 |
| 默认策略切换 | 修改 `DEFAULT_PRESET` 常量即可 |

## 裁决流程

> **AI 必须暂停**: AI 逐条分析并展示判断依据，由用户确认结论（reject / research-only / adopt-with-guardrails）。不可自行裁决。

研究结论进入生产前必须回答：

1. 研究结论是否基于当前代码和当前数据？
2. 是否和当前生产 preset / universe 对比？
3. 是否覆盖必要窗口：1Y / 3Y / 6Y 或需求明确的替代窗口？
4. 是否存在退化？退化是否符合该主体哲学和约束？
5. 是否需要开 REQ？凡涉及 config、UI、payload、正式页展示的变更都必须有 REQ。

### 结论分类

```text
reject                   → 不采纳，记录原因
research-only            → 保留研究价值，不写入生产
adopt-with-guardrails    → 进入 config / Tuner / 正式页，写清边界和回退条件
```

### 退化规则

"有退化不阻塞升级"只适用于继续研究或生成候选，不适用于直接生产落地。

生产落地必须满足：
- 核心目标不低于当前生产配置；或
- 退化被明确接受，且换来更高优先级的目标，并由用户确认。

## 极端集中分析（杠杆策略必须）

> **适用条件**：preset 的 `mbull` > 1.0（合成杠杆）。非杠杆策略跳过此节，直接进入落地流程。

### 为什么需要

合成杠杆策略（gambler 系列，MH=2）会频繁出现**单一持仓**——全部可用火力押在一支 ETF 上。这种集中并非 bug，它是策略全力押注的行为特征。但需要验证：**押注单一方向时，历史上赔率如何**。

### 核心定义：单一持仓 = 极端集中

极端集中 ≠ 权重 > 100%。权重值与杠杆倍数耦合（牛市 158%、熊市 54%），无法跨市态比较。

**正确度量**：调仓后 `len(positions) == 1`——无论杠杆倍数多少，只持有一支 ETF 就是 100% 的火力集中。

```
牛市 mbull=1.58 时单一持仓权重 158% → 极端集中 ✓
熊市 mbear=0.54 时单一持仓权重 54%  → 同样是极端集中 ✓  （之前会被 54% < 100% 漏掉）
gam-1 mbull=0.89 时单一持仓权重 89%  → 同样是极端集中 ✓
```

### 执行

```bash
python scripts/extreme_analyzer.py --preset <preset> --start 2020-01-01
```

> → 预期: 终端输出整体胜率、牛市/熊市事件分布、per-ETF 排名、分类（SAFE/CAUTION/DANGER/NO_DATA）、裁决（PASS/WARN/BLOCK）。
> 结果同时保存到 `research/params/extreme_<preset>.json`。

### 裁决标准

| 裁决 | 条件 | 动作 |
|------|------|------|
| **PASS** | 无 DANGER ETF，整体 win20d ≥ 50% | 继续落地 |
| **WARN** | 存在 CAUTION 或样本不足 ETF，但无 DANGER | 人工审阅后决定是否继续 |
| **BLOCK** | 存在 DANGER ETF（历史性亏损） | **必须**回退：降低 mbull 或提高 MH |

> **AI 必须暂停**: AI 逐项展示 SAFE/CAUTION/DANGER/NO_DATA 列表和整体胜率 + 牛熊分布。由用户确认裁决。不可自行跳过此分析。

### DANGER ETF 的处理

若策略频繁单一押注 DANGER 分类的 ETF：
1. 不意味着该 ETF 本身有毒——只是策略在它身上"孤注一掷"时历史赔率差
2. 若 pool 中 DANGER ETF 不可避免，考虑降低 f7t（提高反转阈值，减少"接飞刀"）或提高 MH（强制分散）
3. 该分析结果应写入 promotion report 的 §七 字段

## 落地流程

```
1. 更新 config/quant_universe.yaml
   → 新增/覆盖 preset 参数块，description 写清约束和性能基线

2. 更新 Tuner
   → 新 preset 加入 SCHOOLS 数组（templates/tuner.html）
   → 若需新控件，同步更新 PARAM_SCHEMA

3. 更新正式页（如适用）
   → payload helper / quant-main.js

4. 验证
   python -m pytest tests/test_quant_contract.py -q
   python -m pytest tests/test_quant_* -q
   python scripts/quant_backtest.py --preset <preset> --start 2023-01-01
```

## 默认策略变更

全项目默认 preset 由 `src/etf_report/core/quant_contract.py::DEFAULT_PRESET` 统一管理。

**触发条件**：preset 已落地 config + 回测验证通过 + 在实盘/Tuner 中观察足够时间后，**独立决策**是否切换默认。落地 config 不等于成为系统默认。

**变更方法**：修改 `DEFAULT_PRESET` 常量，以下入口自动生效：

`quant_backtest.py` / `quant_optimizer.py` / `quant_tuner.py` / `preclose_push.py` / `update_report.py` / `quant_consistency_check.py` / `quant_walkforward.py` / `pool_change.py`

## 接受标准

| 检查项 | 新 preset | 覆盖 preset | 默认切换 |
|--------|----------|------------|---------|
| 回测通过 | EXIT=0，无 NaN | EXIT=0，无 NaN | EXIT=0，无 NaN |
| 核心指标 | 满足 persona 约束 | 不退化或退化有合理解释 | 优于或等于当前默认 |
| Bootstrap | 毁灭概率 ≈ 0% | — | — |
| 极端集中分析 | bul>1.0 时必须，PASS 或 WARN+确认 | bul>1.0 时必须 | bul>1.0 时必须 |
| REQ 追踪 | 必须有 | 必须有 | — |
| config 落定 | 已写入 YAML | 已写入 YAML | 已在 config |

## Ledger

所有变更必须登记到 `research/promoted/README.md`：

```text
date         title                          source                    req        landed_in  status   superseded_by
2026-06-24   gam-2 杠杆优化 (bull=1.58)       gam-2-20260622/report.md  REQ-299    gam-2      active   —
2026-05-28   gam-1 基线 (mdd=-20%)            gam-1-20260616-v4        REQ-250    gam-1      superseded  gam-2
```

字段：`date` `title` `source` `req` `landed_in` `status`（active/rolled_back/superseded/draft） `superseded_by`

详细记录可放在 `research/promoted/records/`，由 ledger 索引。

## 收口

```
1. 更新 research/promoted/README.md
2. 更新 plans/Board.md（如状态变更）
3. 发布或提交
   → 由用户显式触发，按 docs/runbook/release.md 执行
4. stable 同步
   → 发布后如需更新计划任务仓，按 docs/runbook/stable.md 执行
```
