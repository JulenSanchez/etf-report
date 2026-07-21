# 参数优化规范（分组 TP + 等风险面探索）

> **最后更新**: 2026-07-15（分组约束优化框架取代 pool.json 迭代缩界）

## 一、核心设计

不再使用 pool.json 种子库 + 迭代缩界 TPE。当前优化体系基于：
- **YAML 固定槽位**：13~15 个预设（gam-0~N, zen-0~N, act-0~N），参数源在 `config/quant_universe.yaml`
- **指标缓存**：`config/preset_metrics.json`，Tuner 启动时加载，含指纹校验
- **分组 TPE**：`scripts/research_utils.py::optimize_group()`，针对子组联合优化，MDD 约束为硬铁律 -40%
- **DEFAULT_LOCK 单源**：所有参数默认值从 `research_utils.DEFAULT_LOCK` 读取，无散落硬编码

### 参数边界约定

| 参数 | 范围 | 默认(gam-0) | 说明 |
|------|------|------------|------|
| bull | [1.2, 1.8] | 1.80 | 两融上限锁定，不得超过 1.8 |
| bear | [0.5, 1.0] | 1.0 | |
| MH | [2, 6] | 2 | |
| MA | [12, 30] | 18 | |
| C | [0.3, 1.0] | 0.62 | |
| CS | [8, 24] | 16.4 | |
| N | 🔒 40 | 40 | 纯摩擦参数。减小 N 会隐式提升集中度，与头名加成 TB 越俎代庖（REQ-365/366/323） |
| f7_lookback | 🔒 250 | 250 | REQ-382 联合扫参：250 日在 6Y 上最优，缩短无益 |
| f1_s | [4, 16] | 9.6 | |
| f3_s | [2, 8] | 4.79 | |
| f7_up_power | [12, 30] | 23.0 | |
| f7_up_span | [1.5, 5.0] | 3.1 | |
| f7_down_power | [6, 24] | 14.0 | |
| f7_down_span | [1.0, 4.0] | 2.5 | |
| w7 | [5, 25] | 16 | w1/w3 按 gam-0 比例 (71:13) 自动吸收残量 |

## 二、参数树

```
1. 因子评分 ─ "谁是好的"
   ├── F1 子组 ── w1, f1_sensitivity, f1_ema_period
   ├── F3 子组 ── w3, f3_sensitivity, f3_vol_window
   └── F7 子组 ── w7, f7_up_power, f7_up_span, f7_down_power, f7_down_span, F7_window

2. 信心 ─ "下注多少"
   ├── bull=1.80    ✅ 两融上限锁定
   ├── bear=0.60
   └── MA_period=19

3. 集中度 ─ "怎么分"
   ├── MH=2~6       ✅ 网格定
   ├── C, CS, TB    ✅ TPE 精调（代偿组）
   └── band, BS
```

参数可以同时属于功能树的一个位置和多个优化组（如 w7 同时出现在 F7 子组和权重比例组中）。

## 三、research_utils.py

所有优化操作的入口。必读。

| 原语 | 用途 | 示例 |
|------|------|------|
| `backtest()` | 单次回测 | `backtest(MH=2, TB=8, bull=1.80)` |
| `sweep()` | 一维扫描 | `sweep('TB', range(0,9), lock=dict(MH=2))` |
| `group_sweep()` | 分组一维扫描 | `group_sweep('MH',[2,3,4],'TB',lambda mh: range(0,mh*4+1))` |
| `grid_sweep()` | 多维网格 | `grid_sweep({'C':[0.3,0.5],'CS':[0,3,5]}, lock=dict(MH=2))` |
| `group_grid_sweep()` | 分组多维网格 | `group_grid_sweep('MH',[2,3,4],{'C':[...],'CS':[...]})` |
| `pick_best()` | 选最优 | `pick_best(results, group_by='MH', metric='AR')` |
| `pick_multi()` | 多指标选优 | `pick_multi(results, 'MH', ['AR','Calmar','Sortino'])` |
| `optimize_group()` | 分组约束 TPE | `optimize_group('gam-0',['w7','f7_up_power','f7_up_span'],bounds,metric='AR',mdd_bound=-40)` |
| `write_preset_metrics()` | 写指标缓存 | `write_preset_metrics('config/preset_metrics.json', points_dict)` |

`optimize_group()` 自动：加载基线 → enqueue_trial → TPE 探索 → MDD 约束 → 报告 delta。

权重（w1/w3/w7）特殊处理：w1_raw 和 w3_raw 定义比例，w7 确定水平，w1 和 w3 按比例吸收残量。`optimize_group()` 内置此逻辑。

访问路径：`sys.path.insert(0,'scripts'); from research_utils import *`

## 四、preset_metrics.json

```
config/preset_metrics.json
  ├── window: "2020-06-01 ~ 2026-06-01"
  ├── fingerprint: SHA256(preset params + window)  ← 与 YAML 对比防过期
  ├── updated: "2026-07-15"
  └── points: { preset_name → {AR, MDD, Calmar, Sortino, MH, TB} }
```

Tuner `/api/frontier` 读取后按 gam/zen/act 前缀分组，返回 MH 横轴的散点图数据。API 在加载时检查指纹，不一致则返回 `stale: true`。

更新流程：sweep/TPE 产出数据 → 更新 YAML 预设 + 写 preset_metrics.json（一次回测，两份输出，不重跑）。

## 五、旧系统已废除

以下概念和代码在优化上下文中不再使用：
- `pool.json`、`iterative_optimizer.py`、`pareto_optimizer.py`、`quant_optimizer.py`（保留仅供历史 trial 复现参考）
- 分栏优化（`--zone`、`--multi-zone`）、冷启动（Sobol）、缩界（`narrow_bounds`）
- **MDD 前沿曲线**（`frontier_gambler.json` 等）——已被 `preset_metrics.json` + MDD=-40% 硬铁律取代。不存在"5 个 MDD 约束画前沿"的概念
- `max_gross_exposure`——已移除，杠杆由 `ma_bull_pos` 自约束
- `discretize_step`——已替换为 N + TB
- **REQ-324/325/328/329/330**（前沿相关）——全部废弃
