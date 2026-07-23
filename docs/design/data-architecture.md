# 数据架构：筛选池 vs 量化池

> 两组数据物理隔离，命名上不混淆，逻辑上不依赖。

## 核心原则

| | 筛选池 (Screening) | 量化池 (Quant) |
|---|---|---|
| **范围** | 全市场 ~2000 ETF-likes | 当前 `config/quant_universe.yaml` 中的池内 ETF |
| **目录** | `data/screening/` | `data/quant/` |
| **依赖方向** | **不依赖量化池** | 可以依赖筛选池产出 |
| **用途** | REQ-274 筛选工作流 | 回测、Tuner、正式页 |
| **筛选脚本** | `scan_etf_universe.py` | — |

```
data/
├── screening/          ← 筛选池（全市场）
│   ├── .etf_vol_cache.json      Sina hq.sinajs.cn 实时行情
│   ├── .listing_dates.json      Sina getKLineData 上市日期
│   ├── .spot_cache.json         AKShare fund_etf_spot_em 流通市值
│   └── .holdings_cache.json     AKShare fund_portfolio_hold_em 前十大持仓
│
├── quant/              ← 量化池（当前 universe 专属）
│   ├── {code}_daily.csv         腾讯 fqkline 日线（前复权）
│   ├── {code}_weekly.csv        rebuild_weekly_from_daily 周线
│   ├── etf_metadata.json        AKShare 单支查询：规模+持仓+上市日期
│   └── corporate_action_events.json  AKShare fund_cf_em 拆股事件注册
│
└── logs/
```

## 筛选工作流数据 API 表

| 数据 | 接口 | 频率 | 缓存 | 风险 |
|------|------|------|------|------|
| ETF 列表+名称+类型 | AKShare `fund_name_em()` | 按需 | 无（瞬时） | 低 |
| 实时行情(价+量) | 新浪 `hq.sinajs.cn` | ≤4h TTL | `.etf_vol_cache.json` | 批量请求封 IP：50 支/批 + 1.5s 间隔 |
| 上市日期 | 新浪 `getKLineData` scale=240 datalen=5000 | ≤24h TTL | `.listing_dates.json` | ⚠️ 逐支请求，2000 次无间隔→被封。需 ≥0.5s 间隔 |
| 流通市值(AUM代理) | 天天基金 `fundf10.eastmoney.com/jbgk_{code}.html` | ≤168h TTL (季度数据) | `.spot_cache.json` | 低：不同子域名，按 0.35s 间隔逐支请求 |
| 前十大持仓 | AKShare `fund_portfolio_hold_em()` | 按需(首次拉取后缓存) | `.holdings_cache.json` | 逐支请求，仅拉取 top-85 入选 ETF |

## 量化池数据 API 表

| 数据 | 接口 | 频率 | 存储 | 风险 |
|------|------|------|------|------|
| 日线(前复权) | 腾讯 `fqkline` period=day | 每日增量/全量 | `{code}_daily.csv` | 3s 间隔 + 800条/次上限 |
| 周线 | 日线聚合 `rebuild_weekly_from_daily()` | 跟随日线 | `{code}_weekly.csv` | — |
| 份额变动（拆股） | AKShare `fund_cf_em` | 首次调用时检测（session 内缓存） | `corporate_action_events.json` | 按年查询，已有事件去重 |
| 规模+持仓 | AKShare `fetch_etf_metadata.py` (逐支) | ≤30天 TTL | `etf_metadata.json` | 逐支请求，耗时随当前 universe 规模变化 |

## 新增 ETF 的数据流

```
筛选工作流 (scan_etf_universe.py)
  → 发现候选 ETF (不在量化池)
  → 使用筛选 API 拉取全市场数据（不碰 quant/ 目录）
  → 输出 xlsx 供用户审阅
  → 用户确认后 → 换池流程（见 `docs/runbook/v2-quant/pool-change.md`）
    → 拉取日线 CSV → data/quant/
    → 拉取 metadata → 追加到 etf_metadata.json
    → 更新 quant_universe.yaml
```

## 命名约定

- 筛选池变量前缀：`screening_` 或 `screen_`
- 量化池变量前缀：`quant_` 或无前缀（因为它在池内是默认上下文）
- 脚本注释标明依赖方向：`# DEPENDS: screening data only` 或 `# DEPENDS: quant pool`
