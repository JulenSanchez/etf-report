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

## 池子缩容后的数据清理

池子缩容或替换 ETF 后，`data/quant/` 会残留已退出 ETF 的 CSV。清理逻辑：读 `config/quant_universe.yaml` 的 universe + 基准集，删掉不在集合内的 `*.csv`。只删 CSV，不动 `.fresh_today`、`cache/`、`trading_days_*` 等运行时文件。

存为临时脚本后执行（遵循 no-python-inline，勿用 `python -c`）：

```python
# cleanup_stale_csv.py
from pathlib import Path
import yaml

d = Path('data/quant')
cfg = yaml.safe_load(open('config/quant_universe.yaml', encoding='utf-8'))
universe = set(e['code'] for e in cfg['universe'])
benchmarks = {'000016', '000300', '000905', '399006'}
keep = universe | benchmarks

for f in sorted(d.glob('*.csv')):
    if f.stem.split('_')[0] not in keep:
        f.unlink()
        print(f'DEL {f.name}')
print('Done.')
```

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
