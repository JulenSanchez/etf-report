---
description: "基于 research_utils.py 的手动参数扫描 + 前沿刷新，用户精调"
argument-hint: "[preset]"
---

你正在执行 ETF 量化参数手动精调流程。目标：使用 `research_utils.py` 的原子化工具对指定 preset 做参数扫描，更新 `config/preset_metrics.json` 供 Tuner 前沿面板消费。

**当前模式**：前沿由用户精调，不再有自动 TPE 管线。`research_utils.py` 提供 `backtest()` / `sweep()` / `grid_sweep()` / `group_sweep()` / `pick_best()` / `write_preset_metrics()` 等原子，用户按需组合。

## 1. 参数解析

- `$ARGUMENTS` 为空 → 默认跑 `gam-0` 当前参数的验证回测
- `$ARGUMENTS` = 研究描述（如 `MH vs TB sweep`） → 按描述设计扫描方案

## 2. 前置检查

1. **pytest 基线**：`pytest tests/ -x -q` → 必须全绿。
2. **CSV 新鲜度**（仅警告）：检查 `data/*_daily.csv` 最新日期。

## 3. 工作流

```python
from research_utils import *

# 1-D sweep
results = sweep('TB', range(0, 9), lock=dict(MH=2, bull=1.80))

# Group sweep: per-MH sweep TB
results = group_sweep(
    group_by='MH', group_values=[2, 3, 4, 5, 6],
    vary='TB', vary_fn=lambda mh: range(0, mh*4+1),
    lock=dict(bull=1.80),
)

# Multi-dim grid
results = grid_sweep({'C': [0.3, 0.5, 0.71], 'CS': [0, 3, 5]})

# Pick best per group
best = pick_best(results, group_by='MH', metric='AR')

# Write to preset_metrics.json for Tuner consumption
write_preset_metrics('config/preset_metrics.json', {
    f'gam-{i}': r for i, r in enumerate(best)
})
```

## 4. 产出

- 研究结果写入 `research/params/runs/` 带时间戳
- 前沿刷新：`write_preset_metrics()` 更新 `config/preset_metrics.json` → Tuner 自动读取
- 不改 config/quant_universe.yaml presets（命名预设由用户单独决策）

## 5. 高级原子

`research_utils.py` 还提供从旧 `quant_optimizer.py` 提取的 TPE/Grid 优化原子：

```python
from research_utils import ParamSpace, BacktestRunner, optuna_objective, _extract_metrics

# 参数空间
space = ParamSpace(bounds)
for params in space.generate_grid():
    ...

# 回测执行器（带数据预加载缓存）
runner = BacktestRunner("gam-0", DATA_DIR, PROJECT_ROOT, verbose=True)
nav, sig, extra = runner.run_raw(params, "2020-06-01", "2026-06-01")
metrics = runner.run(params, "2020-06-01", "2026-06-01")

# Optuna TPE objective（需 optuna 安装）
import optuna
study = optuna.create_study(direction="maximize")
study.optimize(lambda trial: optuna_objective(trial, runner, cfg, space, baseline_scores), n_trials=100)
```
