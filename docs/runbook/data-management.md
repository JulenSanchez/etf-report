# 数据管理运维

> **触发词**: `刷新数据` `数据管理` `DM面板` `补全空缺` `基准指数`

## 刷新数据 `refresh_data()`

入口: 点击"刷新数据"按钮 → `POST /api/refresh_data` → `refresh_data()`

### 时间判定

```
now < 09:30        → pre_market    (盘前)
09:30 ≤ now < 15:10 → intraday     (盘中)
now ≥ 15:10        → post_market   (盘后)
非交易日            → 跳过
```

### 分支逻辑

```
┌─ [仅盘后] Sina 快路径 ───────────────────────────────────────┐
│  数据源: hq.sinajs.cn (1次HTTP)                              │
│  目标:   54交易ETF + 4基准ETF = 58支                         │
│  写入:   {code}_daily.csv + {code}_weekly.csv                │
│  标签:   "Sina收盘 | 54+4 OK, 0 fail"                       │
└──────────────────────────────────────────────────────────────┘
         │
         ▼
┌─ Gap 检测 + Tencent 增量 ─────────────────────────────────────┐
│  数据源: web.ifzq.gtimg.cn (交易ETF)、update_single()        │
│  触发:   任一ETF的CSV截止日期 < 期望日期                      │
│  期望日期: Sina成功 → prev_td(昨天); Sina失败 → today(今天)  │
│  标签:   "Tencent增量 | 52+2 OK, 0 fail"                     │
└──────────────────────────────────────────────────────────────┘
         │
         ▼
┌─ [仅盘中] Sina 实时价 ───────────────────────────────────────┐
│  数据源: hq.sinajs.cn (1次HTTP)                              │
│  目标:   54交易ETF + 4基准ETF = 58支                         │
│  写入:   CACHE["intraday_cache"] (内存，不写CSV)             │
│  标签:   "Sina实时 | 54+4 ETFs (vol est. EOD)"               │
└──────────────────────────────────────────────────────────────┘
```

### 数据源一览

| | 交易ETF (54) | 基准ETF (4) |
|------|------------|------------|
| 盘后 Sina | `hq.sinajs.cn` → CSV | `hq.sinajs.cn` → CSV |
| 盘后 Tencent (兜底) | `web.ifzq.gtimg.cn` → CSV | `web.ifzq.gtimg.cn` → CSV |
| 盘中 Sina | `hq.sinajs.cn` → intraday_cache | `hq.sinajs.cn` → intraday_cache |
| 回测合并 | `_get_daily_with_cache()` | `_get_benchmark_daily_with_cache()` |

### 刷新数据的功能边界

- **职责**: 确保所有CSV的**最后一行日期**是今天（或盘中实时价已缓存）
- **不负责**: CSV中间空缺的检测和修复 — 那是DM面板的工作
- **设计前提**: CSV数据在刷新之前是连续、健康的

---

## 数据管理面板 (DM)

入口: Tuner → "数据管理" tab

### 功能

| 操作 | 端点 | 说明 |
|------|------|------|
| 查看矩阵 | `/api/data_matrix` | ETF × 日期网格，黄色=盘中，白色=CSV，红色=异常 |
| 状态栏 | `/api/data_status` | CSV截止日期、盘中缓存状态、基准ETF状态 |
| 补全空缺 | `/api/data_fill_gaps` | 逐日比对交易日历，用Tencent API补拉缺失日期 |
| 强制更新 | `/api/data_full_refetch` | 全量重拉指定ETF（含拆股检测） |

### 补全空缺 vs 刷新数据

| | 刷新数据 | 补全空缺 |
|------|---------|---------|
| 检查方式 | `get_last_date` (只看最后一行) | 交易日历逐日比对 (全量审计) |
| 速度 | ~2s (Sina) | 按日期范围和ETF数量 |
| 数据源 | Sina (快) + Tencent (兜底) | Tencent (逐支精确补) |
| 适用场景 | 日常更新、盘中刷新 | 修复数据损坏、长期未更新后恢复 |

### 验证数据完整性

```bash
# 检查某ETF的CSV连续性和最后日期
python -c "
import pandas as pd
df = pd.read_csv(r'data\quant\510300_daily.csv')
dates = pd.to_datetime(df['date'])
print(f'rows: {len(dates)}, range: {dates.iloc[0].date()} ~ {dates.iloc[-1].date()}')
# 检查是否有跳跃
gaps = (dates.diff().dt.days > 3).sum()
print(f'gaps (>3d): {gaps}')
"

# DM面板手动验证
# 1. 打开"数据管理" tab
# 2. 日期范围选最近30天
# 3. 筛选条件选"盘中" (黄色) — 今天应全部为黄色
# 4. 检查基准ETF行 (510050/510300/510500/159915) 同样为黄色
# 5. 点选任意cell → Shift点选 → 右键"补全空缺"
```

### 基准ETF (510050/510300/510500/159915)

- 四支基准ETF在刷新数据中与交易ETF**一视同仁**：同一Sina请求、同一数据源、同一写入路径
- 盘中实时价同时缓存到 `intraday_cache`（`_get_benchmark_daily_with_cache` 合并）
- 回测MA趋势计算通过 `run_tuner_backtest` → `benchmark_daily_merged` 使用合并后数据
- DM面板矩阵自动包含基准ETF（数据源: CSV + intraday_cache）
- DM面板状态栏通过 `benchmarkStatus.intraday` 反映盘中数据可用性
