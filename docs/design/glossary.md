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
| 搜索参数 | TPE 优化的 17 个参数，范围定义在 `PARAM_BOUNDS`，标了 `searchable=true` |
| 固定参数 | 不参与优化的参数（如 `f1_active_days`、`dead_zone`），只从 YAML 或默认值读取 |
| 参数默认值 | 固定参数的缺省值，定义在 `config/defaults.yaml`，所有 YAML preset 共享 |
| 前沿 | 非支配点连成的曲线。Gambler 前端使用。点数取决于 AR 单调性 |
| 槽位展示 | 每 1% MDD 取最优 trial 放到 slider 上。Zen/Actuary 前端使用。不等于前沿 |
| 分栏取样 | 窄界推导时每 5% MDD 各取最优 trial 进 KDE。三派优化共用，不等同于槽位展示 |
| 前沿重验证 | 用当前引擎重新跑一次前沿点的回测，确保 MDD/AR 反映最新代码和数据 |
| 缩界 | 从已有 trial 的参数分布推导更窄的搜索范围，供下轮 TPE 使用 |
| 种子 | pool 中来自 YAML preset 或外部注入的 trial，不经过优化 |
| 流派 | gambler / zen / actuary，三派共享参数空间，区别仅在优化目标和风险轴 |
| MDD 槽位 | 按 MDD 百分比分栏（如每 1% 或每 5%），pool 减负、槽位展示、分栏取样都用到 |
| pool | `research/params/{school}/pool.json`，宽松种子库，TPE 读写 |
| fill-slots | 自动补密度模式——分批跑优化直到前沿非支配点覆盖 MDD [-40,-20] 每个 1% 槽位，满 21 个或连续 2 批无进展自动停 |
| defaults.yaml | `config/defaults.yaml`，非搜索参数的唯一默认值来源 |
| Grill-with-docs | Matt Pocock 技能：拿着术语表审视每个变更，发现漂移当场更新文档 |
| GTD | Getting Things Done，大任务先拆解为小步骤，清空大脑、逐项执行 |
| 分数带 (score_band) | 新标的替换旧持仓时，分数优势必须超过的阈值。防止频繁换仓的"黏着"机制 |
| 变异系数 (CV) | Coefficient of Variation = 标准差 / 均值。衡量 Top-N 分数离散程度——CV 小=分数紧密，CV 大=差距明显 |
| 动态分数带 | score_band 随分数分布自适应调整（REQ-310），紧密时收窄、分散时放宽 |
| 盘后定价交易 | 15:05-15:30 以收盘价固定价格成交，2026-07-06 起覆盖全部 A 股+ETF（REQ-348） |
| preclose_push | 每日收盘前推送信号的自动化脚本，当前 14:50 → 将迁移到 15:05 盘后推送 |
