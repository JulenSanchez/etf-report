# 核心术语

| 术语 | 含义 |
|---|---|
| 项目 / repo | `etf-report` 普通 Git 仓库 |
| 正式页 | 根目录 `index.html`，纯静态 + 预计算 payload |
| payload | `assets/js/*.js` 中的预计算数据，由 Python 生成 |
| Tuner | `quant_tuner.py` 启动的本地 Flask 调参服务，默认 `localhost:5179` |
| v1.0 report | ETF 报告产品线：K 线图表、实时行情、成分股、宏观分析 |
| v2.0 quant | 量化回测产品线：回测引擎、Tuner、信号推送、参数优化 |
| daily | `data/quant/{code}_daily.csv` 中的日线 OHLCV |
| weekly | 由 daily 聚合生成的周线，不直接拉取 |
| intraday | 交易时段实时 OHLCV，只进 Tuner 内存缓存，不写 CSV |
| checkpoint / freeze | F1 抢跑机制的检查点与冻结规则 |
| Promotion | 研究结论被采纳到生产配置，记录在 `research/` |
