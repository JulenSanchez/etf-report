# 参数优化规范（pool.json 种子库 + 迭代缩界 TPE）

> **最后更新**: 2026-07-01 (默认值统一 + fill-slots + 前沿展示策略)

## 一、核心设计

一个 school 一次只跑一个优化进程。每轮从 pool 中取全量 valid trial 推導搜索界。

**非搜索参数默认值**：TPE 只搜索 17 个参数。其余参数默认值来自 `config/defaults.yaml`（唯一来源）。参见 §九。

**前沿展示策略**：Gambler 用非支配前沿（AR 随 MDD 单调）；Zen/Actuary 用每槽最优（Sortino/Calmar 不单调，强制非支配会丢失信息）。

**pool.json = 宽松种子库**。存入任何 params（预设、手动、优化产出），不区分来源。种子条目在首次加载时自动回测填 MDD/COMP。每轮结束后按 MDD 槽位自动减负（band=1.0%，每槽保留最优）。

```
一次优化:
  加载 pool.json (< 5 valid → 冷启动: YAML 种子 → Sobol → TPE 全界)
  → narrow_bounds_from_trials(全量 valid, top-N by COMP)
  → TPE 每轮 30 trial → merge → prune (流派槽位) → save
  → 重复直到收敛

迭代:
  第二次跑 → pool 已有上次产出 → 更窄的界 → 更快收敛
```

## 二、执行

```bash
# 单次优化 (默认 5 轮 × 30 trial)
python scripts/iterative_optimizer.py --school gambler

# 自动补密度 (每批 4 轮, 最多 5 批, 前沿满 21 槽自动停)
python scripts/iterative_optimizer.py --school zen --fill-slots

# 不同流派可并行 (独立 pool)
python scripts/iterative_optimizer.py --school gambler &
python scripts/iterative_optimizer.py --school zen &
python scripts/iterative_optimizer.py --school actuary &
```

## 三、选项

| 参数 | 默认 | 说明 |
|------|------|------|
| `--school` | (必选) | gambler / zen / actuary |
| `--trials-per-round` | 30 | 每轮 TPE trial 数 |
| `--max-rounds` | 5 | 最大轮数 |
| `--cold-trials` | 50 | 冷启动 Sobol trial 数 |
| `--top-n` | 15 | 缩界用 top-N trial |
| `--preset` | 按 school 自动 | YAML preset 名 |
| `--target-metric` | 按 school 自动 | 6y_ar / 6y_sortino |
| `--start-date` | 2020-06-25 | 回测起点 |
| `--seed` | 42 | 随机种子 |
| `--prune-band` | 1.0 | MDD 槽位宽度 (%) |
| `--prune-per-band` | 1 | 每槽保留数 |
| `--sobol-every` | 0 | 每 N 轮注入 Sobol（0=关闭） |
| `--bounds-margin` | 0.3 | 窄界松弛系数 |
| `--bounds-band` | 5 | 分栏宽度（%，0=全局 top-N） |
| `--fill-slots` | false | 自动补密度直到前沿覆盖 21 个 MDD 槽位 |

## 四、三派差异

参数空间、范围、步长、横轴（MDD [-40, -20]）、prune（MDD 槽位 band=1.0%）全部相同。差异仅在纵轴指标和展示策略。

| | gambler | zen | actuary |
|---|---|---|---|
| 目标指标 | 6y_ar | 6y_sortino | 6y_calmar |
| 前沿展示 | 非支配前沿 | 每槽最优 | 每槽最优 |
| 冷启动种子 | gam-0/1/2/3 | zen-1 | act-1 |

## 五、目录结构

```
research/params/
├── gambler/pool.json        ← 种子库 (读+写)
├── zen/pool.json
├── actuary/pool.json
├── frontier_gambler.json    ← 前端消费 (从 pool 派生)
├── frontier_zen.json
└── frontier_actuary.json
```

## 六、手动加种子

```json
// 在 pool.json 中加一行:
{"params": {"w1": 40, "w3": 30, ...}, "source": "manual"}
```

不需要 MDD/COMP。下次加载池子时自动回测填入。

## 七、产出前沿

优化跑完后，重建前沿让前端看到最新结果：

```bash
python -c "
from etf_report.core.quant_contract import build_frontier_output
build_frontier_output(school='gambler')
build_frontier_output(school='zen')
build_frontier_output(school='actuary')
"
# → 产出 frontier_gambler.json / frontier_zen.json / frontier_actuary.json
# → 重启 Tuner 后 /api/frontier 自动读取
```

Gambler 产出非支配前沿点，Zen/Actuary 产出每槽最优（覆盖 [-40,-20] 全部 21 个 MDD 槽位）。gam-0 参考点自动注入 Gambler 图表。参见 §四。

## 八、设计原则

- **宽松入库**：任何 params 可入 pool，不要求 MDD/COMP
- **全量信息**：缩界使用全量有效 trial，不做 MDD 邻域过滤
- **串行迭代**：同 school 串行（利用上一轮的 warm-start），不同 school 可并行
- **自行减负**：每轮结束后按 MDD 槽位自动精简，防止池子膨胀
- **前沿即查询**：前沿从池子实时生成
- **默认值单一来源**：非搜索参数默认值只定义在 `config/defaults.yaml`。禁止在代码、YAML 顶层全局块中重复定义。新增参数时先在 `defaults.yaml` 加默认值。参见下文 §九。
- **优化闭环**：优化完成 → 重建前沿 → 重启 Tuner。全流程跑完即可在前端看到结果。

## 九、默认值规范

**规则**：非搜索参数的默认值唯一来源是 `config/defaults.yaml`。

**禁止**：
- 在 `quant_backtest.py` 里写 `variable = cfg.get("key", 某个数字)`
- 在 `quant_contract.py` 里硬编码 fallback 值
- 在 `quant_universe.yaml` 顶层全局块里定义会被 preset 覆盖的默认值

**正确做法**：
- 新增参数 → `defaults.yaml` 加一行
- 修改默认值 → 只改 `defaults.yaml`
- YAML preset 可以覆盖默认值（如 gam-0 的 `dead_zone=17` 覆盖全局 `25`）
- 验证：`python tests/test_defaults.py` 检查所有代码中的硬编码值是否与 `defaults.yaml` 一致
