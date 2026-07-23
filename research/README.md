# Quant Research — 研究证据库

> 研究证据库。当前生效参数以 `../config/quant_universe.yaml` 为准，当前项目状态以 `../plans/Board.md` 为准。

## 定位

| 目录 | 职责 |
|---|---|
| `params/` | 参数优化报告和结果证据；生产基线 `baseline.yaml` |
| `pool/` | ETF 池研究、候选、换池证据（→ REQ-363） |
| `strategy/` | 策略假说、因子/主体研究、历史实验归档 |

## 工作流入口

| 场景 | Owner 文档 |
|---|---|
| 参数优化 | `../docs/runbook/v2-quant/optimization.md` |
| 换池 | `../docs/runbook/v2-quant/pool-change.md` |
| 发布/提交 | `../docs/runbook/release.md` |

## Git 提交规则

| 可以提交 | 不提交 |
|---|---|
| `README.md` / `report.md` | `*.csv` |
| 小型 `results.json` / `analysis.json` | `*.db` |
| 小型 `results.json` / `analysis.json` | 大型临时 JSON / 日志 |
| 与当前研究仍相关的小型样本 | 一次性脚本 / 可重生成中间产物 |

## 清理原则

以下内容应删除或迁出 research：

1. 旧 preset 命名导致误导的“当前”索引。
2. 缺失脚本、无法复现、且未被未来研究引用的旧方法。
3. 与 ETF/量化研究无关的泛调研材料。
4. 已被后续研究替代的重复详情。

## 新建研究

新建研究项目时复制：

```text
research/_template/
```

最低要求：

- 写清假说和实验范围。
- 写清使用的代码版本、preset、数据截止日。
- 输出 `report.md`；结构化摘要可写 `results.json`。
- 若要投产，更新 `params/README.md` 时间线 + 对应 REQ 状态。
