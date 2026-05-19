# 量化调试规程（本地私有）

**版本**: 1.3
**最后更新**: 2026-05-18
**当前状态**: 调试工具已可用，默认直接启动（不更新数据）；`--auto` 可先增量更新再启动。正式页尚未上线（建设中遮罩）

---

## 执行摘要（快速索引）

> 本文 706 行。先读此摘要，按需跳到对应章节。

### 核心架构（30秒版）

```
数据层：data/quant/*.csv（25支ETF日/周线）←← quant_data_fetcher.py 拉取
         │
         ▼
计算核心：quant_factors.py → quant_backtest.py
         │                  │
         ▼                  ▼
  工坊管线                橱窗管线（建设中）
  quant_tuner.py          quant_build_payload.py
  Flask :5179             → data/quant_payload.js
  交互调参                  → index.html 量化板块
```

**关键约定**：
- 最快启动：`python scripts/quant_tuner.py` → http://localhost:5179
- 长时间回测：必须独立进程（`nohup` 或 `Start-Process`），不能用 AI 会话后台任务
- batch 模式：每次 ≤5 combo，靠 checkpoint 断点续传

### 章节速查

| 你想做的事 | 去哪里 |
|-----------|-------|
| 了解整体架构 / 数据流向 | §1 系统架构 |
| 找某个脚本/配置/数据文件 | §2 文件索引 |
| 数据拉取 / 冷启动 / 增量更新 / 被封处理 | §3 数据管线详解 |
| 启动 Tuner / 参数面板说明 / URL 深链接 | §4 Tuner 使用规程 |
| 参数优化方法 / 搜索策略 / 多窗口验证 / 当前最优结论 | §5 策略调优工作流 |
| **跑回测 / 复用已有回测基础设施 / 分析回测结果** | **§6 回测基础设施与复用指南** |
| 从零搭建环境 | §7 从零搭建量化环境 |
| 某个设计决策的来龙去脉 | §8 设计决策 ADR |
| 报错 / 异常现象排查 | §9 排查指南 |
| 哪些数据需要手动更新 | §10 一次性数据盘点 |

### 当前最优参数（截至 2026-04-30）

| 预设 | 参数 | 3yr Calmar | 适用 |
|------|------|-----------|------|
| `weekly_trend`（推荐） | w1=40,w3=60,W-FRI | 1.60 ✅ | 全市场首选 |
| `daily_aggressive` | w1=40,w2=5,w3=55,daily,sb=5% | 0.77 ❌ | 仅牛市 |

---

## 定位

1. **唯一事实源**：量子系统的架构、数据管线、工具使用规程，只由本文定义。
2. **方法论 vs 工程**：`docs/07-quant-methodology.md` 管"为什么这样打分"（公式、因子语义、截面标准化），本文管"工具怎么用、数据怎么流"。
3. **本地治理文档**：本文位于技能根目录 `runbooks/QUANT_RUNBOOK.md`，只服务本地开发。

---

## 1. 系统架构

### 1.1 工坊 / 橱窗双通道模型

```
                         数据层（共享）
                         =========
data/quant/{code}_daily.csv    (25 支 ETF 日线 OHLCV)
data/quant/{code}_weekly.csv   (25 支 ETF 周线 OHLCV)
config/quant_universe.yaml     (选股池 + 打分权重 + 仓位参数)
config/quant_templates.yaml    (3 套策略模板覆盖)
data/corporate_action_events.json
data/market_regimes.json
data/valuation_history/

        │                           │
        ▼                           ▼

   工坊（Tuner localhost）      橱窗（index.html 静态页）
   ======================      ========================
   quant_tuner.py               暂未接入（建设中遮罩）
     Flask :5179                未来路径：
     交互式调参                    update_report.py → 回测引擎
     实时回测                     → quant_payload.js
     Save to YAML                → window.__QUANT_RUNTIME__
                                  → quant-main.js 渲染

        │
        │  （也可独立运行）
        ▼
   quant_build_payload.py
     直接调回测引擎
     输出 quant_payload.js
```

**核心区别**：
- **工坊**：localhost 交互式，参数即改即跑，适合探索和调优
- **橱窗**：静态预计算结果，浏览用户只看不改，数据提前算好

### 1.2 共享计算核心

两条管线共用同一套因子计算和回测引擎：

```
quant_factors.py              ← F1-F5 因子计算（compute_all_factors / map_f1..map_f5 / confidence_function）
    │
    ▼
quant_backtest.py             ← 回测引擎（load_etf_data / run_backtest）
    │
    ├→ quant_tuner.py         ← Flask 包装，加 HTTP API + preload 缓存
    └→ quant_build_payload.py ← 直接调用，无 Flask 依赖
```

---

## 2. 文件索引

### 2.1 脚本（scripts/）

| 脚本 | 大小 | 职责 | 依赖 |
|------|------|------|------|
| `quant_factors.py` | 19 KB | F1-F5 因子计算 + 连续映射 + 信心函数 | pandas, numpy |
| `quant_backtest.py` | 18 KB | 回测引擎（周度调仓模拟） | quant_factors, pandas |
| `quant_tuner.py` | 42 KB | Flask localhost 调参服务器 | quant_backtest, flask |
| `quant_build_payload.py` | 29 KB | 多模板 payload 生成器 | quant_backtest, akshare |
| `quant_data_fetcher.py` | 4 KB | 拉取 25 支 ETF 历史日线+周线 CSV | akshare |
| `quant_param_search.py` | 16 KB | 权重网格搜索 v1（需 Tuner 运行） | requests |
| `quant_param_search_v2.py` | 11 KB | 粗网格搜索 v2（需 Tuner 运行） | requests |
| `detect_market_regime.py` | 11 KB | 市场状态分类（bull/bear/range） | pandas |
| `detect_market_events.py` | 18 KB | 急涨急跌事件检测 | pandas |

### 2.2 配置（config/）

| 文件 | 职责 |
|------|------|
| `quant_universe.yaml` | 25 支选股池 + 打分权重 + 信心函数 + 仓位参数 + 佣金率 + 2 个预设（weekly_trend/daily_aggressive） |
| `quant_templates.yaml` | 3 套策略模板（conservative/balanced/aggressive）的覆盖参数 |

### 2.3 数据（data/，gitignored）

| 路径 | 职责 |
|------|------|
| `quant/{code}_daily.csv` | 25 支 ETF 日线（date, open, high, low, close, volume, amount） |
| `quant/{code}_weekly.csv` | 25 支 ETF 周线（同上） |
| `quant_payload.js` | `window.__QUANT_RUNTIME__` — Python → JS 的单一交接文件 |
| `market_regimes.json` | 市场状态分类结果（F4 估值因子消费） |
| `valuation_history/` | 估值历史数据（F4 消费） |
| `quant_results/` | 回测 NAV CSV 输出 |
| `param_search/` | 网格搜索结果 CSV |

### 2.4 前端

| 文件 | 职责 |
|------|------|
| `templates/tuner.html` | Tuner SPA 页面（88 KB，ECharts + 滑块面板） |
| `assets/js/quant-main.js` | 正式页量化板块渲染（读 `window.__QUANT_RUNTIME__`） |

---

## 3. 数据管线详解

### 3.1 数据获取（冷启动 + 增量更新）

```bash
# 直接启动 Tuner
python scripts/quant_tuner.py           # 启动，访问 http://localhost:5179

# 如需先更新数据再启动
python scripts/quant_tuner.py --auto    # 自动检测并更新数据，然后启动 Tuner

# 单独更新数据（不启动 Tuner）
python scripts/quant_data_fetcher.py              # 增量更新（默认）
python scripts/quant_data_fetcher.py --full        # 全量重新拉取
python scripts/quant_data_fetcher.py --code 512400 # 只更新一支
```

数据源：腾讯财经 fqkline API（前复权）。输出到 `data/quant/{code}_daily.csv` + `_weekly.csv`。

**冷启动**：首次运行时 CSV 不存在，`quant_data_fetcher.py` 自动全量拉取 25 支 ETF 的历史数据（~3-5 分钟）。

**增量更新**：CSV 已存在时，读取最后一条日期，只拉该日期之后的新数据并追加（~25 秒）。去重后保存。

**实时性要求**：量化回测数据需要每日更新（不像估值历史 PB/BPS 是季更数据）。如需最新数据，先跑 `quant_data_fetcher.py` 再启动 Tuner，或使用 `--auto`。

### 3.2 交互管线（Tuner）

```bash
python scripts/quant_tuner.py        # 默认启动（不更新数据，最快）
python scripts/quant_tuner.py --auto # 先增量更新数据再启动
```

启动流程：
1. `preload()` — 加载全部 ETF 日线/周线 CSV → 内存缓存
2. 预计算基准（HS300）、估值分数、市场状态
3. Flask 服务就绪，端口 5179

**独立窗口启动**（推荐，进程不随终端/IDE 会话关闭而终止）：

```powershell
Start-Process -FilePath "python" `
  -ArgumentList "scripts\quant_tuner.py" `
  -WorkingDirectory "$PWD"
```

> 注意：不要用 AI 会话的后台 Bash 进程启动 Tuner——会话断开进程即终止。也不要用 `cmd.exe /c start`，在 Git Bash 环境下不稳定。

API 端点：

| 端点 | 方法 | 用途 |
|------|------|------|
| `/` | GET | 供给 tuner.html |
| `/api/run` | POST | 提交参数 → 运行回测 → 返回 JSON |
| `/api/presets` | GET | 返回 3 个策略预设参数 + `_universe_options`（全部 ETF 列表，含 code/name/sector/bias） |
| `/api/save` | POST | 将当前参数写回 quant_universe.yaml |
| `/api/kline` | GET | 返回单支 ETF 日线+周线 K 线（含 RSI/EMA） |
| `/api/etf_prices` | GET | 返回 ETF 价格序列（日期范围查询） |

端口冲突处理：启动时检查 5179 端口，若已有进程则通过 `/api/presets` 探测是否为 Tuner，是则复用，否则提示端口被占用。

### 3.3 独立管线（quant_build_payload.py）

```bash
python scripts/quant_build_payload.py
```

不依赖 Flask/Tuner，直接 import `quant_backtest.run_backtest()` 运行回测。为 3 套模板各跑一次回测，组装 `window.__QUANT_RUNTIME__` 写入 `data/quant_payload.js`。

**适用场景**：CI 环境、无需交互调参时、Tuner 不想启动时。

### 3.4 当前正式页管线（建设中）

当前 `update_report.py` 的 `generate_quant_baseline_payload()` 路径：
- Tuner 在跑 → HTTP POST → 真实回测数据
- Tuner 不在 → 写空 payload（`templates: {}`）

**正式页 `index.html` 当前状态**：
- 量化 tab 可点击，但显示"建设中"遮罩
- 原有量化 DOM 结构保留在 `#quant-content-wrapper`（`display:none`）
- `quant_payload.js` 和 `quant-main.js` 仍加载（不报错，空 payload 时跳过渲染）

**未来接入路径**（待管线成熟后）：
1. `update_report.py` 改为直接调 `quant_backtest` 引擎（不依赖 Tuner 运行）
2. 删除 `#quant-construction-mask`，`#quant-content-wrapper` 恢复显示
3. 外部用户可复现的完整数据获取流程

### 3.5 关键交接点

| 交接 | 格式 | 说明 |
|------|------|------|
| CSV → Pandas | `pd.read_csv` | `quant_backtest.load_etf_data()` 读取，两条管线共享 |
| Factors → Scores | Python dict | `compute_all_factors()` + `map_f1..map_f5()` + `confidence_function()`，两条管线共享 |
| Python → JS | `window.__QUANT_RUNTIME__ = {...}` | `quant_payload.js` 是唯一交接文件 |
| JS → DOM | ECharts + innerHTML | `quant-main.js` 读取 `__QUANT_RUNTIME__` 渲染到特定 DOM id |

### 3.6 盘中数据机制（intraday cache）

#### 3.6.1 设计目标

回测和热力图在盘中（9:30–15:10）需要展示当天未收盘的实时数据，但不能把不完整 K 线写入 CSV——CSV 只存已收盘确认的数据。

#### 3.6.2 数据存储

```
CACHE["intraday_cache"] = {
    "512400": {"date":"2026-05-18", "open":1.23, "close":1.25,
               "high":1.26, "low":1.22, "volume":12345, "amount":15432},
    ...
}
```

纯内存，**绝不写入 CSV**。每个 code 最多一条记录，`refresh_data()` 每次拉取时整体覆盖。

数据来源：新浪实时行情 API（`hq.sinajs.cn`），`_fetch_sina_realtime()` 拉取。成交量/额通过 A 股日内 W 形分布模板估算到收盘值（`_estimate_eod_volume()`）。

#### 3.6.3 透明 merge：`_get_daily_with_cache()`

上游消费者（回测引擎、K 线 API、热力图预计算）不直接读 `CACHE["all_daily"]`，而是调 `_get_daily_with_cache(code)`：

```
CACHE["all_daily"][code]   ← CSV 确认数据（到昨天）
        +
CACHE["intraday_cache"][code]  ← 今天的实时估算
        ↓
_get_daily_with_cache() → 返回合并后的 DataFrame
```

合并规则：
- **cache 日期 > CSV 最后日期** → DataFrame 末尾追加一行当天的估算 bar
- **cache 日期 = CSV 最后日期** → 替换最后一行（盘中价格持续刷新，反复覆盖同一行）
- **cache 不存在** → 原样返回 CSV 数据

对上游完全透明——回测/热力图无需区分数据来自 CSV 还是实时估算。

#### 3.6.4 生命周期（`refresh_data()` 内）

| 时段 | 行为 |
|------|------|
| **盘中** (9:30–15:10 交易日) | 拉新浪实时 → 写入 `intraday_cache`；CSV 不做增量更新（等收盘确认） |
| **收盘后** (≥15:10) | CSV 增量拉取（腾讯 API）→ 写入磁盘 → `_reload_csv_to_cache()` → **清空 `intraday_cache`** |
| **盘前/非交易日** | CSV 增量拉取（补历史缺口），无盘中数据 |

核心原则：收盘后今天的 K 线从"内存估算"转为"CSV 持久化"，intraday_cache 归零，第二天重新开始。

#### 3.6.5 成交量估算（`_estimate_eod_volume`）

A 股交易量日内呈 W 形分布（开盘高峰 → 午盘低谷 → 收盘翘尾），简单线性外推会低估。系统使用预计算的 8 段累积分布模板（`_INTRADAY_CUM`，每 30 分钟一段），根据当前时刻的累积占比反推到收盘：

```python
cum_pct = _intraday_cumulative_pct(now)  # 当前已过去的成交量占比
eod_vol = current_vol / cum_pct           # 反推全天成交量
```

### 3.7 数据源运维与排障

> 数据源全景追踪见 `docs/01-数据源与工具生态.md` §9。

#### 当前数据源：腾讯财经 fqkline API

`quant_data_fetcher.py` 调用腾讯财经前复权 K 线 API，参数格式 `?param={code},{period},,,{count},qfq`。

**已知限制**：
- 单次最多 ~800 条（约 3 年日线），`--full` 模式下拉取的是最近 800 条
- 无 `amount` 字段，用 `close * volume * 100` 估算
- 不支持服务端日期范围过滤，增量更新通过客户端裁剪实现
- 沪市 ETF 返回 key 为 `qfqday`（非 `day`），脚本已自动适配

#### API 被封 / 限流

**症状**：
- HTTP 200 但 `code: 1, msg: "param error"`（参数格式错误）
- HTTP 403 / 503 / 连接被拒（IP 被封）

**反爬对策**（已在代码中实现）：
- 自定义 UA + Referer（模拟腾讯自选股浏览器访问）
- 每次请求间隔 3 秒
- 最多重试 3 次，指数退避
- 优先增量模式，减少请求量

#### 收盘冷却期规则

**问题**：A 股 15:00 收盘，但收盘瞬间 API 返回的当日 K 线数据可能未完成结算（成交量/额不完整），导致数据不干净。

**规则**：两条数据管线统一执行 **收盘后 60 分钟冷却期**：

| 管线 | 文件 | 门控函数 | 数据源 |
|------|------|---------|--------|
| 主报告 K 线 | `fix_ma_and_benchmark.py` | `should_drop_incomplete_daily_bar()` | Sina |
| 量化回测 K 线 | `quant_data_fetcher.py` | `_latest_allowed_date()` | 腾讯财经 |

**行为**：
- 当前时间 < 16:00 → 当天数据不拉取/不使用，回退到上一交易日
- 当前时间 ≥ 16:00 → 允许拉取当天数据
- 非交易日 → 当前时间必然 > 16:00，不会误判

**配置**：两条管线共享相同的常量（`MARKET_CLOSE_HOUR=15, COOL_OFF_MINUTES=60`），如需调整冷却时长改对应文件的常量即可。

**被封后的应对**：
1. 确认是哪个源被封：腾讯 fqkline vs 新浪 getKLineData vs AKShare 上游
2. 腾讯 API 被封：换 IP（通常 24-48h 解封）；减少请求频率
3. 新浪/AKShare 被封：不影响量化管线（已改用腾讯），但 fix_ma_and_benchmark.py 和 realtime_data_updater.py 可能受影响
4. 全量重拉（`--full`）比增量更新更容易触发限流，尽量用增量模式

#### 数据源切换历史

| 时间 | 数据源 | 触发原因 |
|------|--------|---------|
| 2026-04 以前 | akshare `fund_etf_hist_sina`（新浪源） | 初始实现 |
| 2026-04-28 | 东财 push2his API（前复权） | REQ-185: 新浪源不复权，改为东财前复权 |
| 2026-05-07 | 腾讯 fqkline API（前复权） | 东财 API IP 被封；腾讯验证可用 |

---

## 4. Tuner 使用规程

### 4.1 启动

```bash
python scripts/quant_tuner.py
# 浏览器打开 http://localhost:5179
```

前置条件：`data/quant/` 下至少有目标 ETF 的 CSV 数据（由 `quant_data_fetcher.py` 拉取）。

### 4.2 参数面板

| 分组 | 参数 | 范围 | 默认 | 说明 |
|------|------|------|------|------|
| 因子权重 | w1..w4 | 0-100 | 40,0,60,0 | F1-F4 权重，不要求归一 |
| 信心函数 | bias | 0-12 | 0 | 偏好标的加分 |
| | conf_type | quadratic/linear/sigmoid | quadratic | 信心曲线形状 |
| | dead_zone / full_zone | 0-100 | 25/65 | 信心阈值（百分比尺度，内部 /100 转 0-1） |
| 仓位 | max_holdings | 1-25 | 6 | Top-N 选股 |
| | disc_step | 1-20 | 5 | 离散化步长（×5%） |
| | rebalance_freq | W-FRI / daily | W-FRI | 调仓频率 |
| | score_band | 0-10 | 0 | 分数带阈值（%，日调仓推荐 3-7%） |
| 因子周期 | ema_period | 5-52 | 20 | F1 EMA 周数 |
| | rsi_period | 5-30 | 14 | F2 RSI 天数 |
| | vol_window | 5-60 | 20 | F3 量比窗口 |
| 映射函数 | f1_sensitivity | 1-20 | 8.0 | F1 sigmoid 灵敏度 |
| | f3_sensitivity | 0.1-5.0 | 1.0 | F3 sigmoid 灵敏度 |
| | f2_dead_zone | 0-5 | 1.5 | F2 双通道死区 |
| 时间窗口 | start_date / end_date | 日期滑块 | 近1年 | 回测起止日期 |
| 标的池 | universe | 逗号分隔 ETF code | 空（=全部） | 限定回测参与标的，空或缺失=使用全部 ETF；至少需 max_holdings 支有数据 |

### 4.3 URL 参数深链接

Tuner 页面支持通过 URL query string 预填参数并自动运行回测：

```
http://localhost:5179/?w1=40&w2=0&w3=60&dead_zone=48&full_zone=65&rebalance_freq=daily&score_band=5&start_date=2024-02-01&end_date=2024-09-30&autorun=1
```

**标的池深链接示例**（仅回测 6 支 ETF）：

```
http://localhost:5179/?universe=512400,515880,512070,513120,512660,512690
```

**支持的全部参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `w1` `w2` `w3` `w4` | int | 因子权重 |
| `bias` | float | 偏好加成 |
| `conf_type` | string | quadratic / linear / sigmoid |
| `dead_zone` `full_zone` | int | 信心阈值（百分比） |
| `max_holdings` | int | 最大持仓数 |
| `disc_step` | int | 离散化步长 |
| `ema_period` `rsi_period` `vol_window` | int | 因子周期 |
| `f1_sensitivity` `f3_sensitivity` | float | 映射灵敏度 |
| `f2_dead_zone` | float | F2 死区 |
| `rebalance_freq` | string | W-FRI / daily |
| `score_band` | float | 分数带（%） |
| `start_date` `end_date` | string | YYYY-MM-DD |
| `universe` | string | 逗号分隔 ETF code，空=全部 |
| `autorun` | string | 1=自动运行（默认），0=只填参数不运行 |

**自适应机制**：URL 参数字段名直接取自 `getParams()` 的 key 集合。新增参数时只需更新 `getParams()` + `setParams()`，URL 自动支持，无需额外注册。新增 string 类型参数需在 `applyUrlParams()` 的字符串判断列表中添加 key。

### 4.4 策略预设

| 预设 | 标签 | 特点 | 适用场景 |
|------|------|------|---------|
| `weekly_trend` | 周频趋势型（推荐） | w1=40,w2=0,w3=60, W-FRI, sb=0 | 全市场环境稳健首选 |
| `daily_aggressive` | 日频攻防型 | w1=40,w2=5,w3=55, daily, sb=5% | 牛市/趋势市专用，震荡市慎用 |

> 旧预设（value/tech/momentum）已替换。新预设基于 REQ-183 多轮参数搜索 + 多窗口验证产出。

### 4.5 Save to YAML

点击"Save to YAML"会将当前滑块参数写回 `config/quant_universe.yaml` 的 `presets` 区。下次 Tuner 启动会读新值。**不会覆盖 scoring/confidence/position 主配置**，只改 presets。

### 4.6 K 线 / 价格 API

- `/api/kline?code=512400&date=2026-04-25` — 返回指定 ETF 在某个调仓日期的日/周 K 线 + RSI/EMA
- `/api/etf_prices?code=512400&start=2024-01-01&end=2026-04-29` — 返回价格/RSI 序列

---

## 5. 策略调优工作流

### 5.1 螺旋优化流程

```
1. 提出假设 → 2. 参数搜索 → 3. 多窗口验证 → 4. 结论与固化 → 5. 新假设
     ↑                                                        │
     └────────────────────────────────────────────────────────┘
```

每轮循环产出：
- 参数搜索结果（CSV / 脚本输出）
- 多窗口验证表（1yr/2yr/3yr + 牛/熊/震荡子窗口）
- 结论更新到 REQ-183.md 螺旋优化日志
- 达标的 preset 固化到 YAML

### 5.2 参数搜索方法论

8 种搜索策略，按场景选择（详见 `docs/08-quant-research-memo.md`）：

| 策略 | 适用场景 | 典型用法 |
|------|---------|---------|
| **Stratum** | 陌生参数空间初探 | 7参数×5-6水平，逐因子扫 |
| **Cascade** | Stratum后精细调 | 只对敏感参数细扫 |
| Full Grid | 参数少（≤3）且维度低 | 权重×权重 |
| One-Factor Sweep | 单因子效应确认 | 控制其他固定，只动1个 |
| Ridge/Hill-Climb | 已知大致最优，微调 | 从当前最优沿梯度走 |
| Funnel | 大空间→小空间逐级 | 粗扫→中扫→细扫 |
| Target Band Filter | 有明确目标范围 | 只保留 Calmar>1.5 的组合 |
| Adversarial Search | 寻找弱点 | 在最差窗口单独优化 |

**默认路径**：Stratum → Cascade（先粗后细，最高性价比）。

### 5.2b 粗扫+精扫实战经验

> 基于 MA 趋势仓位 4 参数优化（2026-05-08）的踩坑总结。

**参数空间**：`ma_trend_period`（8-40）、`ma_bull_pos`（0-100%）、`ma_bear_pos`（0-100%）、`ma_direction_confirm`（开/关）

**实际流程**：

1. **粗扫**（Stratum 思路，但用 Full Grid 而非逐因子）：
   - MA period: 7 个水平（8/12/16/20/26/32/40），步长不等距
   - Bull/Bear: 5×7 = 35 个水平（但 bull≤bear 无效，实际 ~25）
   - Direction: 2 个水平
   - 总计 490 个组合 → 约 2.5 小时（API 模式）
   - 粗扫步长设计原则：**先覆盖边界，步长可以不等距**。MA 的步长 8→12→16→20→26→32→40 就是不等距的，短周期更密（因为短周期变化更剧烈）

2. **精扫**（Cascade 思路）：
   - 取粗扫 top-3 为中心
   - 每参数在中心 ±15% 范围内，步长缩小到原始的 1/3
   - 合并三个中心的重叠范围，避免重复
   - 总计约 50-100 个组合

3. **跨期验证**：
   - 精扫 top-5 用 6yr 周期验证（防过拟合）
   - 只跑 5 次，成本低

**踩坑记录**：

| 问题 | 原因 | 解决 |
|------|------|------|
| AI 后台任务 10 分钟超时被杀 | CodeBuddy/Claude 后台 Bash 有超时限制 | 用 `nohup python -u script.py > log.txt 2>&1 &` 独立进程 |
| API 模式每次回测 15-17 秒 | Flask 串行 + JSON 序列化开销 | 可接受，或改用直接 import（2-3 秒/次） |
| 直接 import 方式脚本卡死不输出 | `sys.stdout` 被 pipe 缓冲 | 用 `PYTHONUNBUFFERED=1` 或 `python -u` |
| 精扫范围合并去重 | top-3 中心可能有重叠参数 | 用 set 合并再排序 |
| Bear ≥ Bull 无效组合 | 滑块范围放开后逻辑冲突 | 生成组合时跳过，UI 层加校验 |

**步长设计经验**：

- 粗扫步长宁大勿小——490 组合跑 2.5 小时已到耐心极限
- 不等距步长OK：MA 周期在 8-20 附近更密（变化更敏感），26-40 更疏
- Bull/Bear 用 5% 或 10% 步长足够（仓位效果是线性的，不需要 1% 精度）
- 精扫步长 = 粗扫步长的 1/3 到 1/2（太大等于没精扫，太小组合数爆炸）

### 5.3 多窗口验证体系

任何参数配置必须通过以下窗口验证才算达标：

**标准窗口**（必须跑）：

| 窗口 | 起止 | 代表 |
|------|------|------|
| 1yr | 近1年 | 近期表现 |
| 2yr | 近2年 | 含一个完整牛熊周期 |
| 3yr | 近3年 | 最严苛考验 |

**牛熊子窗口**（辅助理解，定义基于 HS300 走势）：

| 窗口 | 代表 | 当前定义 |
|------|------|---------|
| bear | 熊市 | 2023-08 ~ 2024-02（HS300 跌 ~20%） |
| choppy | 震荡 | 2024-02 ~ 2024-09（触底反弹+924行情前） |
| bull | 牛市 | 2024-09 ~ 2025-12（924刺激后持续上涨） |

> 注意：子窗口标注基于主观判断 + HS300 走势，非精确量化定义。随时间推移需要更新。

**达标门槛**：

| 指标 | 门槛 |
|------|------|
| 1yr 年化 | ≥ 15% |
| Sharpe | ≥ 1.0 |
| MDD | ≤ -25% |
| Calmar | ≥ 1.5 |
| 3yr Calmar | ≥ 1.0（最差窗口底线） |

**核心指标**：**worst-window Calmar**（所有窗口中最低的 Calmar），不是平均 Calmar。策略稳健性的唯一判据。

### 5.4 当前已知结论（截至 2026-04-30）

#### 周冠军 weekly_trend（推荐默认）

w1=40, w2=0, w3=60, W-FRI, sb=0

| 窗口 | 年化 | Sharpe | MDD | Calmar |
|------|------|--------|-----|--------|
| 1yr | 94.6% | 2.78 | -13.0% | 7.27 |
| 2yr | 76.0% | 1.91 | -14.5% | 5.23 |
| 3yr | 38.9% | 1.26 | -24.4% | 1.60 |
| bear | -22.6% | -1.72 | -19.2% | — |

#### 日冠军 daily_aggressive（牛市专用）

w1=40, w2=5, w3=55, daily, sb=5%

| 窗口 | 年化 | Sharpe | MDD | Calmar |
|------|------|--------|-----|--------|
| 1yr | 103.9% | 2.93 | -13.5% | 7.69 |
| 2yr | 49.9% | 1.58 | -21.4% | 2.33 |
| 3yr | 23.5% | 0.92 | -30.3% | 0.77 ❌ |

日冠军 3yr 不达标，严重过拟合 1yr 窗口。**仅在确认趋势市时使用**。

#### 信心函数关键发现

当前 dz=0.10/fz=0.60 几乎无效（信心值永远≈1.0，永远满仓），因为综合分集中在 0.40-0.70，几乎都 > fz=0.60。

修正 dz/fz 到与分数分布匹配的范围后，熊市 MDD 显著改善：

| 配置 | 熊市 MDD | 熊市年化 | 1yr 年化 | 3yr Calmar |
|------|---------|---------|---------|-----------|
| baseline dz=10 fz=60 | -19.2% | -22.6% | 95.1% | 1.60 |
| dz=45 fz=62 | -15.0% | -24.4% | 92.9% | 0.98 |
| dz=48 fz=65 | -11.6% | -19.1% | 81.0% | 0.97 |
| dz=50 fz=68 | -8.0% | -13.4% | 70.1% | 0.89 |

**权衡**：dz/fz 越高，熊市保护越好，但牛市年化越低。尚未找到既保熊市又不伤牛市的参数。

### 5.5 参数搜索脚本

```bash
# 前提：Tuner 必须在运行
python scripts/quant_param_search.py     # v1: 精细网格（step=10%）
python scripts/quant_param_search_v2.py  # v2: 粗网格（step=20%），2 年窗口
```

输出到 `data/param_search/`（CSV + Markdown 排行榜）。

### 5.6 长时间批量回测的进程管理

> **核心规则**：长时间运行的回测脚本必须作为**独立进程**启动，不能依赖 AI 会话的后台任务机制。

**原因**：CodeBuddy / Claude Code 的后台 Bash 任务有超时限制（通常 10 分钟），超时后进程被杀，回测半途而废。且 AI 会话断开后，后台任务也会随之终止。

**正确做法**（三选一）：

```bash
# 方法 1: nohup + 后台（推荐，最简单）
nohup python -u your_script.py > output.log 2>&1 &
echo $!   # 记下 PID，后续可 kill

# 方法 2: PowerShell Start-Process（完全独立窗口）
Start-Process -FilePath "python" `
  -ArgumentList "-u", "C:\path\to\your_script.py" `
  -WorkingDirectory "C:\working\dir"

# 方法 3: tmux / screen（Linux/Mac，可断开重连）
tmux new -s opt
python -u your_script.py | tee output.log
# Ctrl+B D 断开，tmux attach -t opt 重连
```

**监控进度**：
```bash
tail -f output.log           # 实时查看日志
wc -l output.log             # 检查日志行数（判断是否还在写）
tasklist | grep python        # 确认进程还活着
```

**性能参考**：单次 3yr 回测约 15-17 秒（API 模式）或 2-3 秒（直接 import 模式）。500 组合的网格搜索：
- API 模式：~2.5 小时
- 直接 import 模式：~25 分钟（推荐，但需自行处理 preload）

**脚本编写规范**：
1. 使用 `PYTHONUNBUFFERED=1` 或 `python -u` 确保日志实时写入
2. 每隔 10-20 个组合打印进度（含已完成数/总数/ETA）
3. 中间结果定期落盘（避免进程意外死亡丢失全部数据）
4. 脚本末尾写最终报告到桌面

**batch 模式**（推荐，解决 AI 会话超时问题）：

当通过 AI 会话（CodeBuddy / Claude Code）跑长时间回测时，**即使 nohup 也会被杀**——AI 会话的后台 Bash 有隐式超时，且 nohup 的父 shell 随会话回收。

解法：写一个**每次只跑 N 个 combo 的小脚本**，靠 checkpoint 断点续传，手动循环执行：

```python
# batch 模式核心设计
BATCH = int(sys.argv[1]) if len(sys.argv) > 1 else 5  # 每次跑 5 个

for mp, bull, bear, dc in combos:
    key = combo_key(mp, bull, bear, dc)
    if key in done_keys:        # 跳过已完成的
        continue
    s = bt(mp, bull, bear, dc, ...)
    done_keys.add(key)
    ckpt["coarse_done"] = list(done_keys)
    save_ckpt(ckpt)              # 每个 combo 立刻存 checkpoint
    count += 1
    if count >= BATCH:
        break                    # 跑够就退出
```

执行方式：在 AI 会话前台重复执行 `python -u batch_script.py 5`，每次 ~4min 在超时前完成。

**batch 模式 check list**：
1. **脚本内不启动 tuner**：tuner 启动慢（15s）且进程管理复杂。先手动确认 tuner 在跑
2. **batch size ≤ 5**：5 combo ≈ 4min，留足 AI 前台超时余量（~10min）
3. **每个 combo 立刻写 checkpoint**：用 atomic write（`.tmp` → `os.replace`）防止写坏
4. **API timeout 设 120s**：3-5 次重试 + 递增 backoff
5. **外层 try/except 兜底**：bt() 内部异常不应让整个脚本崩溃
6. **验证 tuner 存活再开跑**：入口 curl `/api/presets`，挂了就退出
7. **tuner 挂了是常态**：长时间运行偶 crash，脚本检测到后 save checkpoint + exit(2)，不尝试自重启
8. **MA=40 等靠后区间优先扫**：本次 MA=40 只完成 20/70，因为排在参数循环最后。如果关心长周期，把参数顺序倒过来或分两轮

### 5.7 成果固化路径

调优后的参数固化在 `quant_universe.yaml` 的 `presets` 区。`update_report.py` 的 baseline 策略读取 `scoring.weights`（主配置区），Tuner 的预设按钮读取 `presets` 区。两条路径独立，需手动同步。

### 5.7 佣金模拟

回测引擎在每次买入/卖出时扣除佣金（默认费率 0.026% = 万0.26，含佣金+过户费，ETF 无印花税）。佣金率在 `quant_universe.yaml` 的 `position.commission_rate` 配置。

关键数据：
- 周调仓：佣金 ~1.2%（43次换仓/年）
- 日调仓+sb=5%：佣金 ~0.74%（36次换仓/年）
- 日调仓+sb=0：佣金 ~2.2%（129次换仓/年）

分数带有效控制佣金——日调仓+sb=5% 的佣金甚至低于周调仓。

---

## 6. 回测基础设施与复用指南

> **核心原则**：需要跑回测或分析回测结果时，**先复用已有基础设施，不要从零写脚本**。

### 6.1 两套回测引擎（不要搞混）

| 引擎 | 入口脚本 | 核心函数 | 依赖 | signal_history 丰富度 |
|------|---------|---------|------|---------------------|
| **quant_backtest** | `scripts/quant_backtest.py` | `run_backtest(start, end, preset, universe_filter=None)` | 无 Flask | 基础（scores, top6, positions, total_target） |
| **quant_tuner** | `scripts/quant_tuner.py` | `run_tuner_backtest(params)` | Flask 进程 | 丰富（+detail, regime, avg_confidence） |

**选择逻辑**：

```
需要跑回测？
  ├─ 涉及 preset（weekly_trend / daily_aggressive）？
  │    ├─ 是 → 用 run_scenarios.py（自动缓存、可并行）
  │    └─ 否 → 需要 Tuner 的交互式参数？
  │              ├─ 是 → 启动 Tuner 进程，调 /api/run
  │              └─ 否 → 用 quant_backtest.py
  └─ 只需分析已有回测结果？
       └─ 用 run_scenarios.load_result() 加载缓存
```

### 6.2 可复用的运行器

#### run_scenarios.py — preset 级回测运行器

```bash
# CLI：跑默认2个preset，结果自动缓存
python scripts/run_scenarios.py

# 指定preset和时间范围
python scripts/run_scenarios.py --presets weekly_trend daily_aggressive --start 2022-01-01 --end 2024-12-31

# 强制重跑（忽略缓存）
python scripts/run_scenarios.py --force

# 串行模式（调试用）
python scripts/run_scenarios.py --no-parallel
```

**Python API**（在分析脚本中加载已跑好的结果）：

```python
from run_scenarios import load_result

nav_df, signal_history = load_result("weekly_trend", "2022-01-01", "2024-12-31")
# nav_df: DataFrame with columns [date, nav]
# signal_history: list of dicts, 每个调仓日的信号记录
```

缓存位置：`outputs/cache/{preset}__{start}__{end}.pkl`，命中则直接返回不重跑。

#### quant_backtest.py — 单次独立回测

```bash
python scripts/quant_backtest.py                     # 默认 weekly_trend, 2023-01-01 起
python scripts/quant_backtest.py --start 2022-01-01 --end 2024-12-31 --preset daily_aggressive
python scripts/quant_backtest.py --output results.csv  # 输出 NAV CSV
```

### 6.3 信号格式差异与推断

`quant_backtest` 的 signal_history 不含 `regime` 和 `detail` 字段。需要 regime 时从 `total_target` 推断：

| total_target | regime | 含义 |
|-------------|--------|------|
| ≥ 0.9 | `ma_above` | 牛市（HS300 在周线 MA 上方） |
| ≤ 0.4 | `ma_below` | 熊市（HS300 在周线 MA 下方） |
| 0.4-0.9 | `mid` | 过渡态（当前配置不会出现） |

示例：

```python
def infer_regime(total_target):
    if total_target >= 0.9:
        return "ma_above"
    elif total_target <= 0.4:
        return "ma_below"
    else:
        return "mid"

regimes = [infer_regime(s["total_target"]) for s in signal_history]
```

### 6.4 常见分析场景速查

| 我想做的事 | 怎么做 |
|-----------|-------|
| 跑两个 preset 对比收益/MDD | `python run_scenarios.py --presets weekly_trend daily_aggressive` |
| 分析某 preset 的 regime 切换 | `load_result()` → 遍历 signal_history，按 `total_target` 推断 regime |
| 分析 ETF 换仓频率 | `load_result()` → 比较 `positions` dict 的变化 |
| 跑自定义参数（非 preset） | 启动 Tuner → `/api/run` POST；或直接调 `quant_backtest.run_backtest()` |
| 多时间窗口验证 | 循环调 `load_result(preset, start, end)`，分别计算指标 |

---

## 7. 从零搭建量化环境

### 一键启动

```bash
python scripts/quant_tuner.py
# 浏览器打开 http://localhost:5179
```

前置：`data/quant/` 下需已有 CSV 数据。

如需先更新数据再启动：
```bash
python scripts/quant_tuner.py --auto
# 自动流程：检测数据 → CSV 不存在则冷启动（~3-5 分钟）/ 已存在则增量更新（~25 秒）→ 启动 Flask
```

### 手动分步（调试用）

```bash
# Step 1（可选）: 更新数据
python scripts/quant_data_fetcher.py              # 增量
python scripts/quant_data_fetcher.py --full        # 全量重拉

# Step 2: 启动 Tuner
python scripts/quant_tuner.py

# Step 3: 交互调参 → 满意后 Save to YAML

# Step 4（可选）: 生成静态 payload
python scripts/quant_build_payload.py
# 输出: data/quant_payload.js
```

### 前置条件

```bash
pip install -r requirements.txt   # pandas, numpy, akshare, flask, pyyaml
```

---

## 8. 设计决策 (ADR)

### ADR-1: 为什么 Tuner 用 Flask localhost

回测引擎是纯 Python（pandas/numpy），浏览器无法直接运行。Flask localhost 提供最小成本的前后端交互：Python 算完返回 JSON，前端 ECharts 渲染。不需要 WebSocket 或持久化服务。

### ADR-2: 为什么 update_report.py 通过 HTTP 调 Tuner

历史原因：Tuner 先建成，`update_report.py` 后接。当时 Tuner 已有完善的 preload 缓存 + 参数注入逻辑，HTTP 调用复用最快。**已知问题**：这导致 Tuner 成为硬依赖，外部用户无法独立生成 payload。未来应改为直接调 `quant_backtest` 引擎。

### ADR-3: F2 双通道设计

F2（RSI 自适应变换）采用双通道架构：z-score 通道（相对历史）+ 绝对位置通道（固定阈值），取较大值。死区 `dead_zone=1.5` 过滤噪声。多窗口验证后，F2 不适合作为默认策略；如重新启用，应作为明确标注的进取/牛市 preset。设计细节见 `docs/08-quant-research-memo.md`。

### ADR-4: 正式页遮罩决策

2026-04-29 决定：量化回测板块对外部用户完全不可用（无 CSV 数据、无数据获取流程、回测依赖本地 Tuner），但页面上没有任何提示，fallback 路径用硬编码假数据。改为：
1. 量化板块加"建设中"遮罩
2. fallback 改为空 payload（不展示假数据）
3. 待管线成熟后正式上线

### ADR-5: 信心函数 dz/fz 与分数分布错配

2026-04-30 发现：信心函数 `dz=0.10, fz=0.60` 几乎完全失效。综合分集中在 0.40-0.70，几乎所有分数 > fz=0.60，导致信心永远=1.0，仓位永远满仓，熊市无保护。

根因：dz/fz 是 0-100 百分比尺度（UI 输入 /100 转内部 0-1），但综合分不是均匀分布在 0-1 上的——实际集中在 0.45-0.70。设置 fz=0.60 相当于"分数超过中下水平就满仓"，太宽松。

修正方向：将 fz 提高到 0.55-0.68 区间（熊市分数 0.41-0.53 < fz → 减仓，牛市分数 0.55-0.73 > fz → 满仓）。但代价是牛市年化下降。**尚未最终确定默认值**。

### ADR-6: 分散度/广度修正方案否决

2026-04-30 测试：在信心函数中加入 top-6 分数标准差（dispersion_threshold）和市场广度（breadth_power）作为仓位修正因子。结果：两个因子在牛市和熊市都降仓，无法区分市场方向。代码已实现但默认关闭（值=0），留作未来参考。

### ADR-7: URL 参数深链接

2026-04-30 实现：Tuner 页面支持 URL query string 预填参数并自动运行。参数字段名取自 `getParams()` 的 key 集合，新增参数自动可用。设计理由：AI 辅助调参时，构造 URL 比手动调滑块高效得多；用户也可通过 URL 分享策略配置。

2026-05-12 扩展：新增 `universe` 参数支持标的池深链接，格式为逗号分隔 ETF code，空或缺失=全部 ETF。

---

## 9. 排查指南

| 现象 | 可能原因 | 排查 |
|------|---------|------|
| Tuner 启动报错 `ModuleNotFoundError: flask` | 未安装 Flask | `pip install flask` |
| Tuner 启动报错 `No CSV data` | `data/quant/` 为空 | 用 `--auto` 启动自动冷启动，或手动跑 `quant_data_fetcher.py` |
| 端口 5179 被占用 | 上次 Tuner 未正常退出 | 检查 `netstat -ano | grep 5179`，kill 进程后重启 |
| 回测返回 NaN / 全零 | CSV 数据缺失或日期不连续 | 检查对应 ETF 的 CSV 文件，必要时 `--full` 重拉 |
| index.html 量化板块空白 | payload 为空（建设中状态） | 正常行为，遮罩层应显示 |
| quant-main.js 报错 `Template not found` | payload 结构异常 | 检查 `data/quant_payload.js` 是否有效 JSON |
| Save to YAML 不生效 | 写入的是 presets 区，非 scoring 主区 | 手动同步 preset 值到 scoring 区 |
| 数据过期（Tuner 回测结果与实际不符） | CSV 未及时更新 | 使用 `--auto` 启动确保增量更新 |

---

## 10. 一次性数据盘点

量化回测依赖的"预计算/一次性数据"，与正式页共享部分数据源：

| 数据 | 存储 | 更新频率 | 生成脚本 | 能否重建 |
|------|------|---------|---------|---------|
| 25 支 ETF 日线/周线 CSV | `data/quant/*.csv` | 日更 | `quant_data_fetcher.py` | **能（冷启动+增量）** |
| 市场状态分类 | `data/market_regimes.json` | 需手动 | `detect_market_regime.py` | 能 |
| 急涨急跌事件 | `data/market_events.json` | 需手动 | `detect_market_events.py` | 能 |
| 成分股 BPS 历史 | `data/stock_bps/*.csv` | 季更（规划中） | `stock_bps_fetcher.py` | 能 |
| ETF 加权 PB 历史 | `data/valuation_history/*_pb.csv` | 季更（规划中） | `stock_bps_fetcher.py` | 能 |
| csindex PE 回填 | `data/valuation_history/*.csv` | 一次性 | `backfill_csindex_pe.py` | 能 |

**当前已自动化的**：量化 CSV（冷启动+增量，通过 `--auto`）

**待自动化的**：市场状态、估值历史（等 REQ-161 周更基建就绪后接入调度）
