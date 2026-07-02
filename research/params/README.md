# params/ — 参数优化证据

> 最后更新: 2026-06-29 (pool.json 设计)

## 当前目录结构

```
research/params/
├── gambler/pool.json          ← gambler 种子库 (自适应, 永不膨胀)
├── zen/pool.json              ← zen 种子库
├── actuary/pool.json          ← actuary 种子库
├── frontier_gambler.json      ← 前端消费的前沿 (build_frontier_output 产出)
├── frontier_zen.json
├── frontier_actuary.json
└── archive/                   ← 旧 iter_*/pareto_*/v3_* 归档
```

## 优化流程

```bash
# 单流派优化 (自动冷启动 → 迭代收敛 → prune → save)
python scripts/iterative_optimizer.py --school gambler

# 产出前沿
python -c "from etf_report.core.quant_contract import build_frontier_output; build_frontier_output(school='gambler')"

# 三派并行
python scripts/iterative_optimizer.py --school gambler &
python scripts/iterative_optimizer.py --school zen &
python scripts/iterative_optimizer.py --school actuary &
```

## 池子行为

- `< 5 valid` → 冷启动: YAML 预设 → [不够] Sobol 50 → [不够] TPE 全界 30
- `>= 5` → 正常迭代: narrow_bounds → TPE → merge → prune (每轮) → save
- prune 规则: gambler 每 0.1% MDD 留最优 AR / zen 留 top-20 Sortino / actuary 每 0.01 bear 留最优 Sortino

## 手动加种子

在 pool.json 中加一行:
```json
{"params": {"w1": 40, "w3": 30, ...}, "source": "manual"}
```
不需要 MDD/COMP。下次优化时自动回测填入。

## 历史目录 (可归档)

- `iter_mdd20/` ~ `iter_mdd40/` — 旧多 target 设计 (已被 pool 取代)
- `iter_act/`, `iter_zen/` — 旧单次优化产出 (数据已迁移到 pool)
- `pareto_gam-2/`, `pareto_test/`, `pareto_verify/` — 旧 pareto_optimizer 产出
- `v3_pareto_full/` — 旧全量 trial
- `gam-*-2026*/`, `act-1-2026*/`, `zen-1-2026*/` — 旧 quant_optimizer 产出
