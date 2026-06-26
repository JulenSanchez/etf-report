# Quant Research — 研究证据库

> research 只保存实验过程、研究报告和 promotion 证据；当前生效参数以 `../config/quant_universe.yaml` 为准，当前项目状态以 `../plans/Board.md` 为准，工作流入口见 `../docs/runbook/workflows.md`。

## 定位

| 目录 | 职责 | 不负责 |
|---|---|---|
| `params/` | 参数优化报告和结果证据 | 维护当前生产参数 |
| `pool/` | ETF 池研究、候选、换池证据 | 维护当前 universe 副本 |
| `strategy/` | 策略假说、因子/主体研究 | 维护当前三派参数 |
| `promoted/` | research → production 的唯一 ledger | 存放未裁决草稿 |
| `baselines/` | 可回放基线快照档案 | 维护当前基线事实源 |

## 工作流入口

| 场景 | Owner 文档 |
|---|---|
| 参数优化 | `../docs/runbook/v2-quant/optimization.md` |
| ETF 筛选 | `../docs/runbook/v2-quant/screening.md` |
| 换池 | `../docs/runbook/v2-quant/pool-change.md` |
| 研究投产 | `../docs/runbook/v2-quant/promotion.md` |
| 发布/提交 | `../docs/runbook/release.md` |

## Promotion 闸门

所有投产结论必须登记：

```text
research/promoted/README.md
```

状态只允许：

```text
active | rolled_back | superseded | draft
```

## Git 提交规则

| 可以提交 | 不提交 |
|---|---|
| `README.md` / `report.md` | `*.csv` |
| 小型 `results.json` / `analysis.json` | `*.db` |
| `research/promoted/**` ledger 和证据 | 大型临时 JSON / 日志 |
| 与当前研究仍相关的小型样本 | 一次性脚本 / 可重生成中间产物 |

## 清理原则

以下内容应删除或迁出 research：

1. 旧 preset 命名导致误导的“当前”索引。
2. 缺失脚本、无法复现、且未被未来研究引用的旧方法。
3. 与 ETF/量化研究无关的泛调研材料。
4. 被 promotion ledger 标记为 rolled_back / superseded 的重复详情。

## 新建研究

新建研究项目时复制：

```text
research/_template/
```

最低要求：

- 写清假说和实验范围。
- 写清使用的代码版本、preset、数据截止日。
- 输出 `report.md`；结构化摘要可写 `results.json`。
- 若要投产，进入 `../docs/runbook/v2-quant/promotion.md`。
