# 术语表

> **分层说明**：本表分三层。AI 与用户沟通时使用**概念层**，读代码时使用**代码层**。用户层记录界面上实际出现的文本。

---

## 一、用户层（界面上看到的）

### Tuner 界面

| 界面文本 | 概念名 | 一句话 |
|---------|--------|--------|
| "刷新数据"按钮 | 数据刷新 | 根据当前时间自动选数据源（盘中=Sina 实时价存入内存，盘后=Sina 收盘价写入 CSV），并补历史缺口 |
| "运行回测"按钮 | 回测执行 | 用当前面板参数跑一次完整回测，结果更新到右侧指标卡 |
| "回测工作坊"标签页 | Tuner 界面 | 策略参数调优 + 回测运行 + 结果查看的主页面 |
| "数据管理"标签页 | DM 面板 | 数据覆盖矩阵——每支 ETF × 每天一个单元格，查看数据完整性、拆股、停牌 |
| "补全空缺"按钮 | 缺口修复 | 逐日比对交易日历和 CSV，用腾讯 API 精准补缺失日期的数据 |
| "强制更新"按钮 | 强制重拉 | 忽略新鲜度标记，重新拉取指定 ETF 的全量或增量数据 |
| "预设"下拉框 | 策略预设 | 预设参数组合（如 gam-0），切换后自动加载对应参数 |

### 刷新数据 — 控制台输出

| 控制台文本 | 含义 |
|-----------|------|
| `Sina收盘 \| 54+4 OK, 0 fail` | 盘后：新浪一次拿到 58 支（54 交易 + 4 基准）的确认收盘价，全部写入 CSV |
| `Sina实时 \| 54+4 ETFs` | 盘中：新浪拿到 58 支的实时价，存入内存供回测使用 |
| `Tencent增量 \| 54+4 OK, 0 fail` | 兜底：腾讯 API 逐支补历史缺口——只在 Sina 失败或多日空缺时出现 |

### DM 面板 — 单元格颜色

| 颜色 | 含义 |
|------|------|
| 绿色 | CSV 有该日期的完整数据 |
| 黄色 | 盘中实时价（intraday），CSV 还没有（盘后写入） |
| 红色 | 数据缺失（CSV 无该日期 + 无盘中实时价） |
| ⚠ 标记 | 检测到拆股事件，待修复 |

### 调仓信号推送

| 界面/通知文本 | 含义 |
|-------------|------|
| `XX/XX 赌徒 调仓信号` | 本地 PC 推送的信号表标题 |
| `XX/XX 赌徒 调仓信号 (远端)` | GitHub Actions 兜底推送的信号表标题 |
| Server酱 | 微信推送通道——信号通过它发到手机 |

---

## 二、概念层（AI 与用户沟通的标准语言）

### 系统架构

| 概念名 | 一句话 | 代码层参考 |
|--------|--------|-----------|
| 正式页 | 根目录 `index.html`，纯静态页面 + 预计算数据，展示 ETF 行情/估值/宏观 | `index.html`, `assets/js/` |
| Tuner | 本地 Flask 调参+回测服务，默认 `localhost:5179` | `scripts/quant_tuner.py` |
| 回测引擎 | 量化回测核心：加载数据 → 算因子 → 跑策略 → 出结果 | `scripts/quant_backtest.py` |
| 策略预设 | 一组固定参数组合（如 gam-0），控制回测全部行为 | `config/quant_universe.yaml` 的 presets 段 |
| 交易 ETF | ETF 池中参与策略调仓的 54 支标的 | `cfg["universe"]` |
| 基准 ETF | 用于判断市场牛熊的四支宽基：510050(上证50)、510300(沪深300)、510500(中证500)、159915(创业板指) | `BM_CODES` |

### 数据管线

| 概念名 | 一句话 | 代码层参考 |
|--------|--------|-----------|
| 数据刷新 | 点击"刷新数据"后的完整流程：时间判定 → 选数据源 → 拉取 → 写存储 → 重建缓存 | `refresh_data()` |
| 新浪行情 | 一次 HTTP 拿到全部 ETF 实时价/收盘价，快（~2s），盘中盘后都用 | `_fetch_sina_realtime()` |
| 腾讯行情 | 逐支 ETF 拉历史日线，慢（~1min/全池），用于补历史缺口 | `_run_incremental_fetch()`, `fetch_etf_kline()` |
| 盘后快写 | 盘后一次性将 58 支 ETF 的确认收盘价写入 CSV（走新浪） | `_sina_batch_append()` |
| 盘中实时入缓存 | 盘中 Sina 拉取实时价后写入 Tuner 内存，回测时临时合并到日线 | `_populate_intraday_cache()` |
| 历史缺口补拉 | CSV 有缺失日期时，逐支通过腾讯 API 补齐 | `_run_incremental_fetch()` |
| 日线合并 | 回测取价的标准路径：CSV 历史收盘价 + 盘中实时价（如有） | `_get_daily_with_cache()` |
| 基准日线合并 | 同上，但针对四支基准 ETF（它们不在交易池中） | `_get_benchmark_daily_with_cache()` |
| 盘中缓存 | Tuner 内存中存的当天实时价，不写 CSV，仅供回测临时使用 | `CACHE["intraday_cache"]` |
| 新鲜度标记 | Tuner 记录"今天已经拉过数据"的标记文件，防止重复拉取 | `FRESH_MARKER` (`.fresh_today`) |
| 数据安全日期 | 盘中返回昨天（不碰未完成的 K 线），盘后返回今天 | `_latest_allowed_date()`, `latest_allowed_close_date()` |
| 收盘冷却时间 | 15:10——在此之前禁止写 CSV，确保写的是确认收盘价而非盘中价 | `COOL_OFF_TIME` |

### 回测核心

| 概念名 | 一句话 | 代码层参考 |
|--------|--------|-----------|
| 因子 | 每支 ETF 的打分依据。F1=趋势动量、F3=估值回归、F7=短期反转 | `quant_factors.py` |
| 牛熊判定 | HS300 的 MA20 均线方向 + 价格在均线上方/下方 → 决定 regime | `_build_ma_trend_cache()`, `build_ma_trend_cache()` |
| 仓位分配 | 从因子分数 → 目标权重 → 实际持仓的计算链：softmax → 离散化 → 步长过滤 → 残量吸收 | `quant_backtest.py` 仓位段 |
| 拆股检测 | 检测 ETF 份额拆分（如 1:2），自动标记 ⚠ 并支持一键修复 | `_detect_pending_splits_from_cache()` |
| 回测窗口 | 回测的起止时间范围，主流口径是滚动 6 年 | `--window` / `--lookback` |

### 推送管线

| 概念名 | 一句话 | 代码层参考 |
|--------|--------|-----------|
| 收盘前推送 | 每个交易日收盘前（14:45-14:55）自动跑回测 + 推送调仓信号到微信 | `preclose_push.py` |
| 远端兜底 | GitHub Actions 上的备用推送——本地 PC 故障时自动接管 | `.github/workflows/signal_push.yml` |
| 信号表 | 推送的核心内容：调仓方向（买入/卖出/持仓不变）、目标比例、现价 | `build_signal_table()` |

### 参数体系

| 概念名 | 一句话 | 代码层参考 |
|--------|--------|-----------|
| 搜索参数 | 参与 TPE 优化的参数（17 个），范围定义在 `PARAM_BOUNDS` | `searchable=true` 的参数 |
| 固定参数 | 不参与优化、从 YAML 或默认值读取的参数 | `LOCKED_PARAMS`, `DEFAULT_LOCK` |
| 参数默认值 | 所有非搜索参数的唯一默认值来源 | `config/defaults.yaml` |

### 研究工具链

| 概念名 | 一句话 | 代码层参考 |
|--------|--------|-----------|
| 前沿 | 非支配点连成的曲线——在同一 MDD 下 AR 最高的 trial | `compute_frontier()` |
| 槽位展示 | 每 1% MDD 取最优 trial 放到 slider | `pick_best()` |
| 分栏取样 | 每 5% MDD 各取最优 trial 进 KDE，用于缩界推导 | `group_sweep()` |
| 缩界 | 从已有 trial 的参数分布推导更窄的搜索范围 | — |
| 种子 | pool 中来自 YAML preset 或外部注入的 trial | `pool.json` |

### 历史术语（保留，仍在使用）

| 术语 | 含义 |
|------|------|
| 拆股 | ETF 份额拆分（如 1:2、1:3），代码中称 share_split |
| 前复权（qfq） | 腾讯 API 参数，自动将历史价格按最新拆股比例调整 |
| 内存清洗（bridge） | 拆股临时补偿：比对 CSV 末笔 close ÷ 实时价 ≈ split_ratio → 内存中历史价格 ÷ ratio |
| 全量重拉 | `--full` 参数重新拉取 ETF 全部历史 K 线，用于拆股后永久修复 |
| 分数带 (score_band) | 新标的替换旧持仓时，分数优势必须超过的阈值，防止频繁换仓 |
| 信号步长 (discretize_step) | 控制 softmax 后目标权重的离散化精度 |
| 执行步长 (execution_step) | 调仓执行参数：控制买卖触发阈值，纯摩擦参数 |
| 名义杠杆 | 策略预设的目标杠杆，如 bull=1.58 / bear=0.60 |
| 实际杠杆 | 调仓后 sum(持仓市值) / NAV，因步长 band 容忍存在日间偏离 |
| 残量吸收 | 末位 ETF 吸收所有剩余购买力，确保资金不闲置 |
| regime 切换纠偏 | 牛/熊切换时目标杠杆大幅跳变，引擎执行大规模买卖追到新目标 |
| 超涨 (overbought) | F7 语境：Z > 0，近期累计收益显著高于历史均值（涨过头），F7 压分 |
| 超跌 (oversold) | F7 语境：Z < 0，近期累计收益显著低于历史均值（跌过头），F7 加分 |
| 盘后定价交易 | 15:05-15:30 以收盘价固定价格成交，覆盖全部 A 股+ETF |
| 昨天 / 今天 | 口语表述 → 系统自动转为交易日语义。昨天 = 上一个交易日，今天 = 最新交易日 |

---

## 三、代码层（仅 AI 读代码时使用，不与用户直接沟通）

### 核心函数

| 函数/变量 | 对应概念 | 所在文件 |
|----------|---------|---------|
| `refresh_data()` | 数据刷新 | `scripts/quant_tuner.py` |
| `_fetch_sina_realtime(cfg)` | 新浪行情拉取 | `scripts/quant_tuner.py` |
| `_sina_batch_append(cfg, date, rt)` | 盘后快写 | `scripts/quant_tuner.py` |
| `_populate_intraday_cache(cfg, now, date, time)` | 盘中实时入缓存 | `scripts/quant_tuner.py` |
| `_run_incremental_fetch(cfg)` | 历史缺口补拉（交易ETF） | `scripts/quant_data_fetcher.py` |
| `_get_daily_with_cache(code)` | 日线合并 | `scripts/quant_tuner.py` |
| `_get_benchmark_daily_with_cache(code)` | 基准日线合并 | `scripts/quant_tuner.py` |
| `_get_weekly_with_cache(code)` | 周线合并（从日线重建） | `scripts/quant_tuner.py` |
| `_build_ma_trend_cache(period)` | HS300 MA 趋势计算（Tuner 启动时） | `scripts/quant_tuner.py` |
| `build_ma_trend_cache(daily, weekly, period)` | HS300 MA 趋势计算（回测引擎内） | `scripts/benchmark_data.py` |
| `run_backtest(preset, ...)` | 回测引擎入口 | `scripts/quant_backtest.py` |
| `run_tuner_backtest(params)` | Tuner 回测入口（含盘中数据合并） | `scripts/quant_tuner.py` |
| `_ensure_tuner()` | Tuner 进程启动管理 | `scripts/preclose_push.py` |
| `_latest_allowed_date(now)` | 数据安全日期 | `scripts/quant_data_fetcher.py` |
| `latest_allowed_close_date(now)` | 数据安全日期（交易日历版） | `scripts/trading_calendar.py` |
| `is_trading_day(date)` | 交易日判定 | `scripts/trading_calendar.py` |
| `last_trading_day(date)` | 上一个交易日 | `scripts/trading_calendar.py` |
| `_is_post_market()` | 是否盘后（≥15:10） | `scripts/quant_tuner.py` |
| `_detect_pending_splits_from_cache()` | 拆股检测（不洗数据） | `scripts/quant_tuner.py` |
| `update_single(etf, full)` | 单支 ETF 数据更新（腾讯 API） | `scripts/quant_data_fetcher.py` |
| `fetch_etf_kline(code, market, ktype)` | 拉取单支 ETF K 线（腾讯 API） | `scripts/quant_data_fetcher.py` |
| `load_etf_as_benchmark(code)` | 加载基准 ETF CSV 数据 | `scripts/benchmark_data.py` |
| `build_index_weekly(daily)` | 从日线重建周线 | `scripts/benchmark_data.py` |

### 核心数据存储

| 变量/路径 | 对应概念 | 说明 |
|----------|---------|------|
| `CACHE["intraday_cache"]` | 盘中缓存 | Tuner 内存 dict，key=ETF代码，value=当日实时 OHLCV |
| `CACHE["all_daily"]` | 全量日线缓存 | Tuner 内存 dict，key=ETF代码，value=完整日线 DataFrame |
| `CACHE["market_regimes"]` | 牛熊状态缓存 | Tuner 内存中已加载的 regime 判定结果 |
| `FRESH_MARKER` | 新鲜度标记 | `data/quant/.fresh_today`，记录今天是否已拉取 |
| `COOL_OFF_TIME` | 收盘冷却时间 | 硬编码值 `15*60+10 = 910`（15:10） |
| `data/quant/{code}_daily.csv` | 日线 CSV | 每支 ETF 的历史 OHLCV，只存确认收盘价 |
| `data/quant/{code}_weekly.csv` | 周线 CSV | 从日线聚合生成 |
| `config/defaults.yaml` | 参数默认值 | 非搜索参数的唯一默认值来源 |
| `config/secrets.yaml` | 密钥配置 | Server酱 sendkey 等敏感信息（不入 git） |
| `config/quant_universe.yaml` | ETF 池 + 策略预设 | 定义 universe（54支）、presets（gam-0等）、因子配置 |

---

## 维护规则

1. **新 UI 标签上线** → 必须在用户层增加对应条目
2. **新函数/变量引入** → 必须在代码层增加条目，同时判断是否需要在概念层新增映射
3. **概念名变更** → 同步更新三层的交叉引用
4. **AI 用函数名跟用户沟通** → 查本表是否有对应概念名。没有 → 问用户是否新增
5. **对话末尾** → 检查本次对话出现的新术语是否已收录
