# Promotion Ledger — 研究结论投产记录

> research → production 的唯一移交台账。当前生产事实源仍以 `../config/quant_universe.yaml` 和 `../plans/Board.md` 为准；本文件只记录研究结论何时、为何、如何进入或退出生产。

## 状态定义

| 状态 | 含义 |
|---|---|
| `active` | 当前仍有效的投产结论 |
| `rolled_back` | 曾经投产，后续已回退 |
| `superseded` | 被后续研究或换池替代 |
| `draft` | 研究候选，尚未投产 |

## Ledger

| 日期 | 内容 | 来源 | 对应 REQ | 落地 | 状态 | 后续 |
|---|---|---|---|---|---|---|
| 2026-05-28 | 三大人设终局参数（旧命名 preset1/2/3） | TPE v2/v3 | REQ-258/253 | `config/quant_universe.yaml` | superseded | 当前 act/zen/gam 以 `plans/Board.md` + config 为准 |
| 2026-05-28 | 三周期等权统一（1Y/3Y/6Y 各 1/3） | 多窗口基线 | REQ-252 | 优化目标函数 | active | — |
| 2026-05-28 | F4/F5 全量清退 | 因子归因+历史结论 | REQ-255 | UI/contract/YAML 移除 | active | — |
| 2026-05-28 | 信心函数仅保留 MA 趋势 | 用户判断 | REQ-256 | Tuner UI 移除4按钮 | active | — |
| 2026-05-28 | 凯利 Bootstrap：三人毁灭概率 0% | Bootstrap 2000路径 | REQ-250 | 归档 research/strategy/kelly | superseded | 旧研究目录已清理，保留 ledger 摘要 |
| 2026-05-28 | C/CS 缩放 bug 修复 | Tuner 对比测试 | REQ-252 | `quant_contract.py` + `tuner.html` | active | — |
| 2026-05-29 | 精算师30维子参数落地 | sub-TPE | REQ-253 | `quant_universe.yaml` | superseded | 当前 act-1 以 config 为准 |
| 2026-06-12 | 德国替换 159561 → 513030 | REQ-274 同组 PK | REQ-274 | 候选记录 | rolled_back | 当前 config 仍为 159561，旧详情文件删除 |
| 2026-06-12 | 粮食 159698 → 159825 候选 | REQ-274 同组 PK | REQ-274 | 未投产 | rolled_back | 分类修正后保留 159698 |
| 2026-06-12 | 稀土 516150 → 562800 候选 | REQ-274 同组 PK | REQ-274 | 短暂候选 | superseded | R15 移除 562800 |
| 2026-06-16 | R15 换池：+9/-4，油气→石油，池子 49→54 | `research/pool/rounds/2026-06-16.md` | REQ-274 | `config/quant_universe.yaml` | active | 当前 universe 仍以 config 为准 |

## 规则

1. 所有 promotion 先登记本 ledger，再改 production。
2. 详细研究报告可以位于 `research/params/`、`research/pool/`、`research/strategy/`，但不能替代本 ledger。
3. 被回退或替代的结论不再保留重复详情文件；只在本 ledger 留摘要和状态。
