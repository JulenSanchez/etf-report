# params/ — 参数优化

> 本文记录参数优化结论和证据，不作为当前生效参数事实源。当前生效值以 `../../config/quant_universe.yaml` 为准；参数映射契约见 `../../scripts/quant_contract.py`。

## Current Best (2026-05-27)

### 凯利最优 (preset1) — 主力

| 参数 | 值 | 来源 |
|------|-----|------|
| ema_deviation (w1) | 0.461 | TPE 权重优化 2026-05-27 |
| volume_ratio (w3) | 0.363 | TPE 权重优化 2026-05-27 |
| log_return_deviation (w7) | 0.176 | TPE 权重优化 2026-05-27 |
| **concentration (C)** | **0.4** | **Sortino×Calmar TPE CS∈[0,10] 2026-05-27** |
| **c_sensitivity (CS)** | **8.6** | **同上** |
| S×C | 8.9 | vs 原 preset1 7.0 |

其余参数同下。

### 趋势锚定 (preset3) — 原 preset1, 基线对照

| 参数 | 值 | 来源 |
|------|-----|------|
| ema_deviation (w1) | 0.461 | 同 preset1 |
| volume_ratio (w3) | 0.363 | 同 preset1 |
| log_return_deviation (w7) | 0.176 | 同 preset1 |
| concentration (C) | 0.5 | 浓度扫描 2026-05-20 |
| c_sensitivity (CS) | 10.0 | 动态 C 网格搜索 2026-05-25 |
| f7_window | 20 | Phase 1 |
| f7_k | 3.5 | Phase 1 |
| f7_t | 15.0 | Phase 1 |
| ema_period | 5 周 | 浓度扫描 |
| score_band | 0.03 | Phase 2 xval |
| f1_sensitivity | 8.0 | Phase 3 |
| f3_sensitivity | 1.5 | Phase 3 |
| **基线 6Y** | +910.0%, MDD -17.9% | 2026-05-26 |

### 趋势锚定(静态) (preset2) — CS=0 对照

| 参数 | 值 | 来源 |
|------|-----|------|
| concentration | 0.5 | 静态 C |
| c_sensitivity | 0.0 | 禁用动态 C |
| **基线 6Y** | +528.0%, MDD -16.3% | 旧 preset1 |

## 历史探索

| 目录 | 标题 | 日期 | 核心发现 |
|------|------|------|---------|
| `F7-optimization/` | F7 因子历史优化 | 2026-05-13 | f7_window=10 最优, w7/k/t 全量扫描 |
| `F7F6-joint-optimization/` | F7+F6 联合优化 | 2026-05-15 | Phase1 粗扫→Phase2 交叉→Phase3 补充→随机收尾, 全局最优确认 |
| `concentration-sweep/` | daily_aggressive 浓度参数扫描 | 2026-05-20 | C=0.5 最优（1Y +101.3%, 3Y +124.7%）, C≥0.7 衰退, 换手率随 C 单调递增 |
| `spot-check-20260521/` | preset1 参数敏感度 spot-check | 2026-05-21 | max_holdings=4(+711% 6Y)>>6(+479%), MA=20w(+545%)>26w, C=1.0(+567%)>0.5, 日频>>周频; preset4=集中趋势(C=1.0/MH=4/MA=20w)组合验证 |

## Methodology

- **Phase 1: 粗扫** — 单因子独立扫描，大范围大步长，识别敏感参数和最优区域
- **Phase 2: 交叉** — Top 2 敏感参数网格交叉，打破局部最优
- **Phase 3: 补充** — 遗漏参数（EMA/score_band/sensitivity）补充扫描
- **Phase 4: 随机收尾** — 200 组随机组合过滤测试，确认无遗漏潜力区
- **行为分析** — 极端行情 checkpoint 对比验证

## 已知陷阱

1. **单因子扫描的基线污染**：Phase 3 的 score_band 结论被错误基线（f1=12, f3=2.0）污染，交叉验证纠正。单因子结论不可直接信任，必须交叉验证。
2. **局部最优≠全局最优**：每个参数的最优值并集不一定是全局最优组合。

## Tried & Failed

| 尝试 | 结果 | 日期 |
|------|------|------|
| **F6 动能衰竭惩罚因子** | 2026-05-26 正式废弃。全窗口 F7 碾压 F6(6Y +910% vs +383%, MDD -17.9% vs -21.1%)。F6+F7 仅比纯 F7 多 +18%。条件触发式逃顶不如 F7 连续波动率偏离。preset2 删除，代码保留。 | 2026-05-26 |
| F7: w7=0.25 | 过度惩罚, 逃顶滞后, 3Y 落后 F6 +15.7pp | 2026-05 (优化前) |
| F6: f6_rsi_thresh=85, drop=4% | 触发极稀, 几乎裸奔 | 2026-05 (优化前) |
| F6: score_band=0.05 | Phase 3 误判为最优, 交叉验证推翻 | 2026-05-15 |
| vol_window=14 或 26 | 20 日最优, 偏离显著劣化 | 2026-05-15 |

## Applied

- 2026-05-15: F7F6 联合优化结论已应用到 presets
- 2026-05-20: concentration 0.0→0.5（浓度扫描确认 C=0.5 在 1Y/3Y 上最优）
- 2026-05-21: 新增 preset4（集中趋势）— max_holdings 6→4, C 0.5→1.0, MA 26w→20w
- 2026-05-25: **动态 C 参数 (c_sensitivity)** 发现与网格搜索。C=0.5, CS=10 在所有窗口(1Y/3Y/6Y)的 MDD 均≤18%，6Y 总收益+910% vs 旧静态 C 的+528%。preset3(动能保护)删除，旧 preset1 下移为 preset3(静态对照)。详见 `research/cs_grid_search.json`。
- 2026-05-27: **凯利最优 (C,CS)**——Sortino×Calmar TPE CS∈[0,10] 找到 C=0.4, CS=8.6 为最优。preset1↔preset3 互换。详见 `research/strategy/kelly/README.md`。
- 2026-05-27: **因子权重 TPE 优化**——w1/w3/w7=0.461/0.363/0.176 (S×C=8.9 vs 原7.0)。已应用到 preset1/3。详见 `research/strategy/factor_weights/results.json`。

## TODO

- CS 渐近线 ~1400%，如需突破考虑 sigmoid 公式替代线性
- 0.5 基准值(σ 中位数)可优化为滚动窗口版本
- MA Trend 参数与动态 C 的交互效应待验证
