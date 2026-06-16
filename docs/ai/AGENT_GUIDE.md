# etf-report AI 协作指南

本文件只记录 AI 执行任务时容易误判的项目约定。冷启动入口见 `AGENTS.md`，项目运行入口见 `README.md`。

## 任务路由

| 任务 | 入口 |
|---|---|
| 更新正式页报告 | `python scripts/update_report.py` 或 `python scripts/report_site/update_report.py` |
| 健康检查 | `python scripts/health_check.py` 或 `python scripts/report_site/health_check.py` |
| 启动 Tuner | `python scripts/quant_tuner.py` 或 `python scripts/quant_lab/quant_tuner.py` |
| 生成量化 payload | `python scripts/quant_build_payload.py` 或 `python scripts/quant_lab/quant_build_payload.py` |
| 发布 | 先读 `docs/ops/release.md`，不要直接 push |
| ETF 池变更 | 先读 `docs/ops/pool-change.md`，按逐支 SOP 执行 |

## 高风险规则

1. 策略逻辑变更前先保存基线；没有基线不动策略逻辑。
2. ETF 池变更必须同池对比，且总收益率不低于基线 95%，最大回撤恶化不超过 2 个百分点。
3. 数据源失败不等于代码 bug；遇到 403/503/timeout 先降频或等待，不要反复重跑。
4. GitHub Pages 当前直接服务源码仓 `main` 的根目录 `index.html` 和 `assets/`；本轮不要把它们移到 `web/`。
5. 不自动 push、不 force push；远端更新必须经用户确认。

## 核心术语

| 术语 | 含义 |
|---|---|
| 项目 / repo | `etf-report` 普通 Git 仓库 |
| 正式页 | 根目录 `index.html`，纯静态 + 预计算 payload |
| payload | `assets/js/*.js` 中的预计算数据，由 Python 生成 |
| Tuner | `quant_tuner.py` 启动的本地 Flask 调参服务，默认 `localhost:5179` |
| report-site | v1.0 正式页生成、校验、发布链路 |
| quant-lab | v2/v3 量化回测、Tuner、信号推送、研究链路 |
| daily | `data/quant/{code}_daily.csv` 中的日线 OHLCV |
| weekly | 由 daily 聚合生成的周线，不直接拉取 |
| intraday | 交易时段实时 OHLCV，只进 Tuner 内存缓存，不写 CSV |
| checkpoint / freeze | F1 抢跑机制的检查点与冻结规则 |
| Promotion | 研究结论被采纳到生产配置，记录在 `research/promoted/` |
