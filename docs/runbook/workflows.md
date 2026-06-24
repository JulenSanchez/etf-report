# 工作流索引

本文是操作入口索引。每个工作流只维护一个 owner 文档；其他文档只链接，不复制步骤。

| 触发词 | 工作流 | Owner 文档 | 第一事实源 | 最小验证 | 产物 |
|---|---|---|---|---|---|
| 发布 | 安全发布 | `docs/runbook/release.md` | `plans/Board.md` | `python scripts/update_report.py` + release Phase 0-8 | commit / push / Pages |
| 提交 | 快速提交 | `docs/runbook/release.md` | `git diff --cached` | release Phase 0-4 + Phase 6 | commit |
| 更新报告 | 正式页本地生成 | `docs/runbook/v1-report.md` | `scripts/update_report.py` | `python scripts/update_report.py` | `index.html` + payload |
| 筛选 ETF | ETF 候选筛选 | `docs/runbook/v2-quant/screening.md` | `scripts/scan_etf_universe.py` | 生成候选表 + 人工审阅 | 候选清单 |
| 换池 | ETF 池变更 | `docs/runbook/v2-quant/pool-change.md` | `config/quant_universe.yaml` | 逐支拉数 + `gam-1` 基线对比 | config diff + research/pool 记录 |
| 优化 `<preset>` | 参数优化 | `docs/runbook/v2-quant/optimization.md` | `config/quant_universe.yaml` | `analysis.json` + report 门禁 | `research/params/<run>/` |
| promotion | 研究投产 | `docs/runbook/v2-quant/promotion.md` | `research/promoted/README.md` | 1Y/3Y/6Y + 必要 bootstrap/一致性验证 | config / promoted ledger / REQ |
| 启动 Tuner | 本地调参 | `docs/runbook/v2-quant/tuner.md` | `scripts/quant_tuner.py` | `python -m pytest tests/test_quant_contract.py -q` | Tuner UI/API |
| 刷新量化数据 | CSV 数据刷新 | `docs/runbook/v2-quant/data-fetch.md` | `scripts/quant_data_fetcher.py` | 指定日期刷新 + `tests/test_quant_data_cache.py` | `data/quant/*.csv` |
| stable | stable 仓与计划任务 | `docs/runbook/stable.md` | Windows Task Scheduler + stable repo | LastTaskResult + 手动 bat 复现 | stable 快进更新 |
| 审计 | 项目审计 | `docs/runbook/audit.md` | 代码实现 | L0-L3 审计报告 | 问题清单 / 修复建议 |

## 规则

1. 工作流步骤只在 owner 文档维护。
2. 其它文档需要提到流程时，只链接 owner 文档。
3. 发布、提交、push、stable 更新都必须走 `docs/runbook/release.md` / `docs/runbook/stable.md`，不得藏在业务 SOP 中自动执行。
