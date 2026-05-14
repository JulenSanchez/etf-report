# ETF 报告系统 — 架构设计

**设计理念**: 数据驱动、配置化、可观察

## 架构概览

```
腾讯财经 API (K线主源) ─┐
新浪财经 API (实时行情) ─┤→ 数据获取 → CSV 存储 → 多因子计算 → HTML 注入 → GitHub Pages / 企微
AKShare (估值/企业行动) ─┘
```

六层结构：
1. **数据获取层** — 腾讯财经 API（日/周 K 线，前复权）、新浪财经 API（实时行情 + 基准指数）、AKShare（中证指数 PE/PB 历史、基金拆分/折算）
2. **数据处理层** — 份额变动自动识别、数据清洗（不复权场景）、MA/EMA 均线计算、基准对标、估值百分位
3. **数据存储层** — `data/quant/*.csv`（每 ETF 日/周线独立文件）+ `data/valuation_history/` + `corporate_action_events.json` + `market_regimes.json`
4. **量化引擎层** — F1-F7 七因子（EMA 偏离/RSI 自适应/量比/估值/波动率/动能衰竭/对数收益偏离）+ 信心函数（Regime/MA Trend/DD Trigger）+ 周度调仓回测
5. **报告生成层** — JavaScript 对象注入 HTML + 量化 payload 独立 JS，100% 样式保证
6. **调参工具层** — Quant Tuner（Flask localhost:5179），滑块调参 + 一键回测 + K 线复盘

## 核心设计原则

### 数据+模板分离

HTML 中的 `<script>const klineData = {...};</script>` 是数据容器。
更新只需替换 JSON 值，不触碰 HTML/CSS。样式永不漂移。

### 配置化管理

所有参数集中在 `config/config.yaml`（330+ 行）和 `config/holdings.yaml`（60 个成分股）。
新增 ETF：编辑 YAML，无需改代码。支持环境变量覆盖。

优先级：环境变量 > 命令行参数 > config.yaml > 代码默认值。

### 结构化日志

JSON Lines 格式，多级别（DEBUG/INFO/WARN/ERROR）。
终端彩色输出 + 文件输出。5 个脚本 100% 覆盖。

### 健康检查

26 项自动检查，集成在每次执行流程末尾，并额外覆盖解释层鲜度。非交易日或编辑态内容场景下出现少量 WARN 属正常。

## 模块依赖

```
数据管线（日更）:
  config_manager.py → logger.py → update_report.py (主控)
                                      ├─ fix_ma_and_benchmark.py → data_cleaning.py
                                      ├─ realtime_data_updater.py
                                      ├─ valuation_fetcher.py → valuation_engine.py + stock_bps_fetcher.py
                                      ├─ editorial_fetcher.py + compliance_filter.py
                                      └─ health_check.py + verify_html_integrity.py

量化管线（回测 + Tuner）:
  trading_calendar.py + benchmark_data.py + quant_data_utils.py
      → quant_factors.py → quant_backtest.py
              ├→ quant_tuner.py (Flask localhost:5179)
              ├→ quant_build_payload.py (静态 payload)
              └→ quant_data_fetcher.py (腾讯财经 K 线 CSV 增量更新)
```


## 设计决策 (ADR)

| ADR | 决策 | 理由 |
|-----|------|------|
| 数据注入方式 | JavaScript 对象注入 | 最小改动，100% 样式保证，无额外依赖 |
| 配置格式 | YAML | 新增 ETF 从 4h → 15min，支持环境变量覆盖 |
| 日志格式 | JSON Lines | 机器可解析，便于搜索和分析 |
| 健康检查 | 26 项全量（含解释层鲜度） | 问题早期发现，自动化诊断 |
| 量化因子 | F1-F7 七因子 + 信心函数 | 覆盖趋势/动量/量价/估值/波动率/衰竭/对数收益 |
| 资产池 | 34 支 ETF，按扇区分类 | 权益宽基 + 行业 + 跨境 + 红利，可配置扩展 |

## 后续演进

- 实盘调仓信号生成器（盘后一键输出调仓指令）
- 统一数据获取管线（合并 quant_data_fetcher + fix_ma_and_benchmark + realtime_updater）
- 参数网格搜索自动化（sweep_f7_full.py 替代废弃的 quant_param_search）
- 测试覆盖补全（核心量化模块：backtest / tuner / build_payload）
