# 量化数据刷新运维

> **触发词**: `拉数据` `刷新 K 线` `数据刷新`

量化 CSV 位于 `data/quant/`，由 `scripts/quant_data_fetcher.py` 维护。日线是主数据，周线由日线重建。

## 常用命令

```bash
# 增量刷新全部 ETF
python scripts/quant_data_fetcher.py

# 全量重拉
python scripts/quant_data_fetcher.py --full

# 补拉指定日期范围
python scripts/quant_data_fetcher.py --start YYYY-MM-DD --end YYYY-MM-DD

# 单支 ETF
python scripts/quant_data_fetcher.py --code 512400 --start YYYY-MM-DD --end YYYY-MM-DD
```

## 数据源与时段

| 场景 | 数据源 | 写入 |
|---|---|---|
| 盘中 | Sina 实时行情 | 只进 Tuner `intraday_cache`，不写 CSV |
| 盘后 | 腾讯/本地确认收盘数据 | 写入 daily CSV 并重建 weekly |
| 非交易日 | 增量补缺口 | 写入 CSV |

## 收盘冷却期

收盘后不要立即反复刷新。若数据源尚未确认收盘价，等待后再刷新，避免把盘中数据写入 CSV。

## 故障排查

| 症状 | 处理 |
|---|---|
| `No CSV data` | 运行 `python scripts/quant_data_fetcher.py --full` 或单支补拉 |
| 数据日期不新 | `python scripts/quant_data_fetcher.py --start <today> --end <today>` |
| QDII 停牌/缺口 | 先看 `config/quant_universe.yaml` 的 qdii/active 状态，再查数据源返回 |
| 接口 403/timeout | 降低频率、等待冷却，不要循环重试 |

## 最小验证

```bash
python scripts/quant_data_fetcher.py --start YYYY-MM-DD --end YYYY-MM-DD
python -m pytest tests/test_quant_data_cache.py -q
```
