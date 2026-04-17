# ETF 报告系统 — 架构设计

**设计理念**: 数据驱动、配置化、可观察

## 架构概览

```
新浪财经 API → 数据获取 → 均线计算 → JSON 存储 → HTML 注入 → 本地/企微/GitHub
```

四层结构：
1. **数据获取层** — 新浪财经 API（K线 + 实时行情 + 基准指数）+ AKShare `fund_cf_em`（基金拆分/折算）
2. **数据处理层** — 份额变动自动识别、数据清洗、MA5/MA20/MA50 均线计算、基准对标
3. **数据存储层** — `etf_full_kline_data.json` + `etf_realtime_data.json` + `corporate_action_events.json`

4. **报告生成层** — JavaScript 对象注入 HTML，100% 样式保证

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
config_manager.py → logger.py → update_report.py (主控)
                                    ├─ fix_ma_and_benchmark.py → data_cleaning.py
                                    ├─ realtime_data_updater.py
                                    └─ health_check.py
```


## 设计决策 (ADR)

| ADR | 决策 | 理由 |
|-----|------|------|
| 数据注入方式 | JavaScript 对象注入 | 最小改动，100% 样式保证，无额外依赖 |
| 配置格式 | YAML | 新增 ETF 从 4h → 15min，支持环境变量覆盖 |
| 日志格式 | JSON Lines | 机器可解析，便于搜索和分析 |
| 健康检查 | 26 项全量（含解释层鲜度） | 问题早期发现，自动化诊断 |

## 后续演进

- 多源数据聚合（东财、同花顺）+ 自动容错降级
- 缓存机制减少 API 调用
