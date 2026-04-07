# 每日更新参数分类 - 可视化指南

**创建日期**: 2026-04-07  
**文档版本**: 1.0  
**适用范围**: ETF 投资报告系统

---

## 📊 参数分类总览

```
配置系统 (config.yaml)
├── 🔴 静态参数 (从不变更)
│   ├── ETF 列表与代码
│   ├── 基准指数配置
│   ├── API 端点地址
│   └── 文件路径配置
│
├── 🟢 每日更新参数 (必须每天更新)
│   ├── K线数据（日线/周线）
│   ├── 实时行情数据
│   ├── 日期信息（报告日期/数据截止）
│   ├── MA 均线数据
│   └── 成分股实时数据
│
├── 🟠 可选调整参数 (季度/半年调整)
│   ├── K线显示天数 (display_days)
│   ├── MA均线参数 (warmup_days)
│   ├── 请求间隔 (request_delays)
│   └── 颜色配置 (colors)
│
└── 🟡 系统参数 (无需手动修改)
    ├── fetch_days (自动计算)
    ├── 日志配置
    └── 系统检查列表
```

---

## 🟢 **每日更新的参数** - MUST UPDATE DAILY

### 1. K线数据（存储在 `data/etf_full_kline_data.json`）

| 参数 | 位置 | 内容 | 更新频率 | 示例 |
|------|------|------|---------|------|
| **日线数据** | kline → daily | 收盘价、开盘价、最高、最低、成交量 | **每天** | `[{"date": "2026-04-07", "close": 2850.5}]` |
| **周线数据** | kline → weekly | 周度聚合数据 | **每周** | `[{"week": 14, "close": 2850.5}]` |
| **MA 均线** | 计算生成 | 20日、50日、200日均线 | **每天** | `{"ma20": 2840, "ma50": 2820}` |

**触发方式**: `python update_report.py` → Step 1: K线数据获取

---

### 2. 实时行情数据（存储在 `data/etf_realtime_data.json`）

| 参数 | 内容 | 更新频率 | 示例 |
|------|------|---------|------|
| **ETF涨跌幅** | 当日价格变化 | **每天** | `{"512400": {"change": 0.5, "pct_change": 0.15}}` |
| **成分股涨跌幅** | 持仓股票涨跌 | **每天** | `{"600016": {"name": "民生银行", "pct_change": 1.2}}` |
| **交易量** | 成交额、成交量 | **每天** | `{"volume": 50000000, "amount": 127500000}` |
| **最后更新时间** | 行情时间戳 | **每天** | `"2026-04-07 15:00:00"` |

**触发方式**: `python update_report.py` → Step 4: 实时行情获取

---

### 3. HTML 中的日期信息

| 参数 | 配置位置 | 含义 | 更新频率 | 示例 |
|------|---------|------|---------|------|
| **报告日期** | html_update → locators | 显示日期 | **每天** | `2026年04月07日` |
| **数据截止** | html_update → locators | 数据有效期 | **每天** | `2026-04-07 15:00` |
| **生成时间** | html_update → locators | 报告生成时刻 | **每次更新** | `2026-04-07 16:44:30` |

**位置**: `outputs/index.html` 中的以下标记：
```html
<div>报告日期: 2026年04月07日</div>
<div>数据截止: 2026-04-07 15:00</div>
<div>生成时间: 2026-04-07 16:44:30</div>
```

**触发方式**: `python update_report.py` → Step 5: HTML 更新

---

## 🔴 **静态参数** - 通常不变

### ETF 列表与配置

```yaml
# ✅ 这些参数基本不变，除非调整投资组合
etfs:
  - code: "512400"        # 代码不变
    name: "有色金属ETF"    # 名称不变
    market: "sh"           # 交易所不变
    benchmark:
      code: "sh000300"     # 基准指数代码不变
      name: "沪深300"      # 基准指数名称不变
```

**变更场景**: 
- 添加新的 ETF：`config.yaml` 中新增一条
- 删除 ETF：从列表中移除对应条目
- 变更基准指数：修改 benchmark 配置

**频率**: 按需（通常几个月到半年改一次）

---

### API 端点与参数

```yaml
api:
  sina:
    kline_endpoint: "https://money.finance.sina.com.cn/..."    # 不变
    realtime_endpoint: "https://hq.sinajs.cn/list="            # 不变
    timeout: 10              # 不变
    encoding: "gbk"          # 不变
    request_delays:
      kline_fetch: 0.2       # 不变（除非 API 限流）
      realtime_fetch: 0.3    # 不变（除非 API 限流）
```

**变更场景**: 
- API 地址变化（新浪财经更新 API）
- 请求限流需要调整延迟

**频率**: 按需（通常 1-2 年）

---

## 🟠 **可选调整参数** - 季度/半年调整

### K线显示参数

```yaml
kline:
  daily:
    display_days: 60        # 🟠 可调整：显示多少天的数据
    warmup_days: 19         # 🟠 可调整：MA预热周期
    fetch_days: 79          # 🟡 自动计算（display_days + warmup_days）
  
  weekly:
    display_weeks: 52       # 🟠 可调整：显示多少周的数据
    warmup_weeks: 19        # 🟠 可调整：MA预热周期
    fetch_weeks: 71         # 🟡 自动计算
```

**调整说明**:
- `display_days: 60` → 改为 120 可显示更久的数据
- `warmup_days: 19` → 改为 49 计算 50日均线（需要 49 天预热）
- 改变这些参数会自动影响 `fetch_days` 的计算

**更新频率**: 每季度审查一次（Q1, Q2, Q3, Q4）

---

### 颜色配置

```yaml
html_update:
  colors:
    positive_change: "#10b981"    # 🟠 可调整：上涨颜色（绿）
    negative_change: "#ef4444"    # 🟠 可调整：下跌颜色（红）
    neutral_change: "#9ca3af"     # 🟠 可调整：平盘颜色（灰）
```

**调整说明**: 修改这些颜色值后，下次生成的报告会应用新颜色。

**更新频率**: 按需（如品牌色彩调整）

---

## 🟡 **系统参数** - 自动计算，不要手动修改

```yaml
# ❌ 不要手动修改这些字段
fetch_days: 79       # 自动 = display_days (60) + warmup_days (19)
fetch_weeks: 71      # 自动 = display_weeks (52) + warmup_weeks (19)

# ❌ 这些文件名通常固定
data_files:
  kline: "etf_full_kline_data.json"
  realtime: "etf_realtime_data.json"
  fund_flow: "fund_flow_data.json"
```

---

## 📈 **日常更新流程**

### 每天执行（推荐：交易日 15:00 之后）

```bash
# 一键更新所有参数
python scripts/update_report.py

# 输出的数据参数：
# ├─ K线数据 (新增当日数据)
# ├─ MA均线 (重新计算)
# ├─ 实时行情 (获取最新数据)
# ├─ 日期信息 (更新为今日)
# └─ HTML报告 (生成新报告)
```

**更新的文件**:
- `data/etf_full_kline_data.json` (新增 1 行数据)
- `data/etf_realtime_data.json` (更新所有数据)
- `outputs/index.html` (更新日期和数据)
- `logs/update_report_YYYYMMDD.jsonl` (新增日志)

---

## 📊 参数更新日历

### 日常维护

| 频率 | 操作 | 参数 | 命令 |
|------|------|------|------|
| **每天** | 数据更新 | K线 + 实时数据 + 日期 | `python update_report.py` |
| **每周** | 验证完整性 | 运行健康检查 | `python health_check.py` |

### 定期维护

| 频率 | 操作 | 参数 | 方式 |
|------|------|------|------|
| **每月** | 审查日志 | 查看异常记录 | 查看 `logs/` 目录 |
| **每季度** | 调整显示范围 | display_days, warmup_days | 编辑 config.yaml |
| **半年一次** | 检查 API | kline_endpoint, realtime_endpoint | 测试 API 可用性 |
| **按需** | 调整投资组合 | ETF 列表 | 编辑 etfs 配置 |

---

## 🔄 参数变更影响分析

```
┌─────────────────────┐
│  修改 config.yaml   │
└──────────┬──────────┘
           │
    ┌──────┴──────┐
    ▼             ▼
 立即生效      重新计算所需
 - 文件路径    - K线显示范围
 - ETF代码     - MA均线周期
 - API端点     - 预热数据量
 
┌─────────────────────────────┐
│ 下次运行 update_report.py   │
└──────────┬──────────────────┘
           ▼
    ┌──────────────────────┐
    │ 应用新配置生成报告   │
    └──────────┬───────────┘
               ▼
       ✅ 报告已更新
```

---

## 💡 最佳实践

### ✅ DO's

1. **每天自动更新** - 设置 cron 任务自动执行
   ```bash
   # 每个交易日 15:30 执行一次
   0 15 * * 1-5 python /path/to/update_report.py
   ```

2. **监控健康检查** - 每周检查一次系统状态
   ```bash
   python health_check.py --json > weekly_report.json
   ```

3. **定期备份配置** - 修改前先备份
   ```bash
   cp config/config.yaml config/config.yaml.backup
   ```

4. **版本控制配置** - 追踪配置变更历史
   ```bash
   git add config/ && git commit -m "Update config"
   ```

### ❌ DON'Ts

1. **不要手动修改 K线 JSON** - 使用脚本自动更新
2. **不要修改 fetch_days** - 这是自动计算的
3. **不要修改 API 端点** - 除非新浪财经官方更新
4. **不要删除成分股配置** - 除非从投资组合移除 ETF

---

## 📋 参数变更清单

### 当需要变更时：

**新增 ETF**:
```yaml
# 在 etfs 列表中添加
- code: "新代码"
  name: "新ETF名称"
  market: "sh/sz"
  benchmark:
    code: "基准代码"
    name: "基准名称"

# 然后在 holdings.yaml 中添加成分股
```

**调整显示范围**:
```yaml
# 从 60 天改为 90 天
kline:
  daily:
    display_days: 90  # 改这里
    warmup_days: 19   # 保持不变或调整
    fetch_days: 109   # 会自动重新计算
```

**更新 API**:
```yaml
# 如果新浪财经 API 变化
api:
  sina:
    kline_endpoint: "新端点地址"
    realtime_endpoint: "新端点地址"
```

---

## 📞 常见问题

**Q: 修改了 config.yaml 后要重启吗？**  
A: 不需要，下次运行脚本时会自动重新加载配置。

**Q: 可以同时修改多个参数吗？**  
A: 可以，但建议一次修改一个类别，便于排查问题。

**Q: 如何回滚参数变更？**  
A: 有备份就用备份文件覆盖，或使用 git 恢复。

**Q: 如何验证参数是否生效？**  
A: 运行 `health_check.py` 检查配置加载是否成功。

---

## 🎯 总结

```
每日必须更新的数据 (自动化):
├── K线数据 (OHLCV)
├── MA均线 (20/50/200日)
├── 实时行情 (ETF和成分股)
└── 日期信息 (报告日期、数据截止)

偶尔需要调整的参数 (手动):
├── K线显示范围 (每季度)
├── ETF投资组合 (按需)
├── 颜色配置 (按需)
└── API参数 (按需)

绝不手动修改的字段 (系统级):
├── fetch_days (自动计算)
├── API端点 (除非官方更新)
└── 系统检查列表 (系统维护)
```

---

**文档版本**: 1.0  
**最后更新**: 2026-04-07  
**下一步**: 设置自动化定时任务
