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
| 拆股 | ETF 份额拆分（如 1:2、1:3）。AKShare `fund_cf_em` 自动检测，代码中称 share_split |
| 前复权（qfq） | 腾讯 `fqkline` API 参数，自动将历史价格按最新拆股比例调整。拆股当天有延迟 |
| 内存清洗（bridge） | `refresh_data` 中（盘后+盘中有 intraday cache 时）的拆股临时补偿：比对 CSV 末笔 close ÷ 实时价 ≈ split_ratio → 内存中历史价格 ÷ratio。已调整则自愈跳过 |
| 全量重拉 | `--full` 参数重新拉取 ETF 全部历史 K 线，用于拆股后永久修复 CSV |
| corporate_action_events | AKShare 检测到的拆股事件注册表，Tuner 启动时自动更新 |
| pool | `research/params/{school}/pool.json`，宽松种子库，TPE 读写 |
| fill-slots | 自动补密度模式——分批跑优化直到前沿非支配点覆盖 MDD [-40,-20] 每个 1% 槽位，满 21 个或连续 2 批无进展自动停 |
| defaults.yaml | `config/defaults.yaml`，非搜索参数的唯一默认值来源 |
| Grill-with-docs | Matt Pocock 技能：拿着术语表审视每个变更，发现漂移当场更新文档 |
| GTD | Getting Things Done，大任务先拆解为小步骤，清空大脑、逐项执行 |
| 分数带 (score_band) | 新标的替换旧持仓时，分数优势必须超过的阈值。防止频繁换仓的"黏着"机制 |
| 信号步长 (discretize_step) | 仓位分配参数：控制 softmax 后目标权重的离散化精度（最大余数法）。与 C、CS、max_holdings 共同决定"押注集中度"。粗粒度值（如 0.165）隐性地放大集中度——相邻分被推入同一 bucket。YAML key `position.discretize_step` |
| 执行步长 (execution_step) | 调仓执行参数：控制买卖触发阈值。超配卖出需超过 full band（step×NAV），非末位低配买入需超过 half band（step×NAV×0.5），末位无条件吸残量。纯摩擦参数，隔离实验显示对长期收益几乎无影响。YAML key `position.execution_step`，未配置时 fallback 到 `discretize_step` |
| 三兄弟 (C/CS/signal_step) | 仓位集中度的三个参数：concentration（softmax 温度）、c_sensitivity（C 的动态灵敏度）、signal_step（离散化精度）。三者存在有机互动，粗粒度 signal_step 等价于隐性 C 放大。REQ-365 拆分后待系统性研究 |
| 名义杠杆 (nominal leverage) | 策略预设的目标杠杆，如 gam-0 bull=1.58 / bear=0.60。定义在 YAML 的 `ma_bull_pos` / `ma_bear_pos` |
| 实际杠杆 (actual leverage) | 调仓后 sum(持仓市值) / NAV。因步长 band 容忍，与名义杠杆存在日间偏离。6Y 回测 bull 均值 1.60（名义 1.58）、bear 均值 0.63（名义 0.60） |
| 残量吸收 (末位吸残量) | `_execute_rebalance` 第三步的末位特殊处理：无论偏离是否达 half band，末位 ETF 吸收所有剩余购买力（上限 max_gross_exposure）。确保资金不闲置，可能使末位仓位略高于目标 |
| regime 切换纠偏 | 牛/熊 MA 穿线切换时，目标杠杆大幅跳变（如 0.60→1.58），引擎执行大规模买卖追到新目标，之前累积的超配/低配残留被清零。这是步长偏差在长期归零的核心机制 |
| 变异系数 (CV) | Coefficient of Variation = 标准差 / 均值。衡量 Top-N 分数离散程度——CV 小=分数紧密，CV 大=差距明显 |
| 动态分数带 | score_band 随分数分布自适应调整（REQ-310），紧密时收窄、分散时放宽 |
| 盘后定价交易 | 15:05-15:30 以收盘价固定价格成交，2026-07-06 起覆盖全部 A 股+ETF（REQ-348） |
| preclose_push | 每日收盘前推送信号的自动化脚本，当前 14:50 → 将迁移到 15:05 盘后推送 |
| 超涨 (overbought) | F7 语境：Z > 0，近期累计收益显著高于历史均值（涨过头）。F7 对超涨侧压分（分数 < 0.5），由 `f7_up_power` / `f7_up_span` 控制曲线形状 |
| 超跌 (oversold) | F7 语境：Z < 0，近期累计收益显著低于历史均值（跌过头）。F7 对超跌侧加分（分数 > 0.5），由 `f7_down_power` / `f7_down_span` 控制。REQ-375 起两侧参数独立 |
| F7 power（幂次） | F7 形状参数：区间内曲线的幂次。越大越"压扁"——小偏离几乎不给分，接近饱和半径才快速起量。旧名 `f7_t` / `f7_t_os` |
| F7 span（饱和半径） | F7 形状参数：Z-score 的饱和点。\|Z\| = span 处分数打满（0 或 1），超出后走切线线性外推。旧名 `f7_k` / `f7_k_os` |
| 昨天 / 今天 | 口语表述，系统内自动转换为交易日语义——"昨天" = 上一个交易日（`last_trading_day`），"今天" = 最新交易日（当日为交易日时即当日，否则回退到上一个交易日）。AI 必须内在地按交易日历过滤，不存在裸"前一日历日"语义。相关函数：`latest_allowed_close_date`（盘中返上一个交易日，盘后返当日） |
