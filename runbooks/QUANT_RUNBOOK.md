# Quant Runbook — 量化系统运维手册

**版本**: 2.0  
**最后更新**: 2026-05-20  
**定位**: 本文只负责量化系统的本地运维：启动、刷新数据、检查状态、生成正式页 payload、跑一致性检查和排障。

> 系统入口 / 文件职责 / 变更路由：`../QUANT_SYSTEM.md`  
> 回测引擎契约：`../docs/BACKTEST_ENGINE.md`  
> 当前参数与资产池事实源：`../config/quant_universe.yaml`  
> 参数契约实现：`../scripts/quant_contract.py`

---

## 1. 快速命令

以下命令默认在技能根目录执行：

```bash
cd /path/to/etf-report
```

### 1.1 启动 Tuner

```bash
python scripts/quant_tuner.py
# 打开 http://localhost:5179
```

### 1.2 独立进程启动 Tuner（Windows 推荐）

避免 IDE 会话关闭导致服务退出：

```powershell
Start-Process -FilePath "python" `
  -ArgumentList "scripts\quant_tuner.py" `
  -WorkingDirectory "C:\Users\julentan\StockMarket\.claude\skills\etf-report"
```

### 1.3 检查 Tuner 状态

```bash
curl http://localhost:5179/api/data_status
curl http://localhost:5179/api/param_schema
curl http://localhost:5179/api/presets
```

关注：

| 字段 | 含义 |
|---|---|
| `ready` | Tuner 是否已完成预加载 |
| `csvLatestDate` | `data/quant/*.csv` 最新日期 |
| `intradayCacheDate` | 盘中实时缓存日期 |
| `intradayCacheCount` | 盘中缓存 ETF 数量 |

### 1.4 刷新量化数据

```bash
python scripts/quant_data_fetcher.py              # 增量更新，默认选择
python scripts/quant_data_fetcher.py --code 512400 # 只更新单支 ETF
python scripts/quant_data_fetcher.py --full        # 全量重拉，谨慎使用
```

### 1.5 强制重拉特定日期数据

当怀疑某几天的 CSV 数据有问题（如盘中价被错误写入），先删后拉：

```bash
# 预览（不执行）
python scripts/strip_csv_dates.py --dry-run 2026-06-01 2026-06-02

# 删除 6/1~6/2 的行
python scripts/strip_csv_dates.py 2026-06-01 2026-06-02

# 然后刷新
# 在 Tuner 页面点「刷新数据」或 POST /api/refresh_data
```

原理：`refresh_data` 发现 CSV 缺数据 → 自动走增量拉取路径补全。

### 1.6 跑一致性检查

```bash
python scripts/quant_consistency_check.py --preset preset1 --start 2025-01-01 --end 2026-05-19
python scripts/quant_consistency_check.py --preset preset2 --start 2025-01-01 --end 2026-05-19
python scripts/quant_consistency_check.py --preset preset3 --start 2025-01-01 --end 2026-05-19
```

一致性检查对比：

```text
Direct preset: run_backtest(preset=...)
Tuner contract: preset -> tuner params -> config_override -> run_backtest(...)
```

如果 FAIL，先修一致性，再继续调参或发布。

---

## 2. 日常运维流程

### 2.1 盘后调参前

1. 更新量化 CSV：
   ```bash
   python scripts/quant_data_fetcher.py
   ```
2. 启动 Tuner：
   ```bash
   python scripts/quant_tuner.py
   ```
3. 打开：
   ```text
   http://localhost:5179
   ```
4. 检查右侧“参数原理 → 参数契约”：应显示 `schema v1 · ... params`。
5. 检查 `/api/data_status`，确认数据日期符合预期。

### 2.2 调参后保存参数

1. 在 Tuner 页面点击“保存参数”。
2. 参数会写入 `config/quant_universe.yaml` 的目标 preset。
3. 立刻运行：
   ```bash
   python scripts/quant_consistency_check.py --preset preset2 --start 2025-01-01 --end 2026-05-19
   ```
4. 如参数作为研究结论沉淀，更新：
   ```text
   research/params/README.md
   research/strategy/README.md
   ```

### 2.3 改回测逻辑后

必须至少执行：

```bash
python -m pytest tests/test_quant_contract.py tests/test_quant_backtest_execution.py tests/test_quant_consistency.py
python scripts/quant_consistency_check.py --preset preset2 --start 2025-01-01 --end 2026-05-19
```

若改动影响 `run_backtest()` 的语义，同时更新：

```text
docs/BACKTEST_ENGINE.md
QUANT_SYSTEM.md（如变更路由或契约变化）
```

---

## 3. 数据管线运维

### 3.1 文件位置

| 数据 | 路径 | 说明 |
|---|---|---|
| ETF 日线 | `data/quant/{code}_daily.csv` | date/open/close/high/low/volume/amount |
| ETF 周线 | `data/quant/{code}_weekly.csv` | 由日线重建或数据源拉取 |
| 市场状态 | `data/market_regimes.json` | 部分因子/历史逻辑会消费 |
| 估值历史 | `data/valuation_history/` | F4 估值相关 |
| 正式页 payload | `assets/js/quant_payload.js` | `window.__QUANT_RUNTIME__` |

### 3.2 当前数据源

量化 K 线：腾讯财经 fqkline API，前复权。  
脚本：`scripts/quant_data_fetcher.py`

已知约束：

- 有请求频率限制。
- 增量更新优先，少用 `--full`。
- `amount` 可能为估算值：`close * volume * 100`。
- 收盘后有冷却期，避免拿到未完成 K 线。

### 3.3 收盘冷却期

当前量化管线：

```text
MARKET_CLOSE_HOUR = 15
COOL_OFF_MINUTES = 10
```

含义：15:10 后才允许把当天 K 线视为已确认数据。盘中数据只进 Tuner 的 intraday cache，不写入 CSV。

### 3.4 盘中 intraday cache

Tuner 盘中会把新浪实时行情临时合并进内存：

```text
CACHE["intraday_cache"]
```

规则：

- 只在内存中存在。
- 不写入 `data/quant/*.csv`。
- 收盘后 CSV 更新成功会清空 cache。
- 回测、K 线 API、热力图读取时通过 Tuner 内部合并视图使用。

---

## 4. Tuner 运维

### 4.1 主要 API

| API | 用途 |
|---|---|
| `/` | Tuner 页面 |
| `/api/data_status` | 数据新鲜度 / Tuner ready 状态 |
| `/api/param_schema` | 参数契约 schema |
| `/api/presets` | 从 `quant_universe.yaml` 读取 preset 并转为前端参数 |
| `/api/run` | 提交当前参数并运行回测 |
| `/api/save` | 保存当前参数到 preset |
| `/api/kline` | 单 ETF K 线复盘数据 |
| `/api/etf_prices` | ETF 价格序列 |
| `/api/heatmap_data` | 涨跌热力图数据 |

### 4.2 参数契约

参数转换统一由：

```text
scripts/quant_contract.py
```

负责：

```text
preset_to_tuner_params()
tuner_params_to_config_override()
tuner_params_to_preset_patch()
validate_tuner_params()
get_param_schema()
```

新增或修改 Tuner 参数时，不要只改 HTML。必须同步：

```text
scripts/quant_contract.py
templates/tuner.html
tests/test_quant_contract.py
QUANT_SYSTEM.md（如契约说明变化）
```

### 4.3 端口冲突

默认端口：

```text
5179
```

如页面打不开：

1. 访问 `/api/data_status` 判断服务是否在线。
2. 如端口被旧进程占用，使用：
   ```bash
   python scripts/kill_tuner.py
   ```
3. 重新启动 `python scripts/quant_tuner.py`。

---

## 5. 正式页 payload 运维

正式页读取：

```text
assets/js/quant_payload.js
```

由以下路径生成：

```text
update_report.py -> generate_quant_baseline_payload()
```

当前实现：

1. 从 `config/quant_universe.yaml` 读取 `preset2`。
2. 通过 `quant_contract.py` 转为 Tuner 参数。
3. 调用 Tuner `/api/run` 生成 1 年 / 3 年回测结果。
4. 写入 `assets/js/quant_payload.js`。

注意：

- 不要手改 `assets/js/quant_payload.js`。
- 如果 Tuner 没启动，payload 可能为空或沿用旧文件，需看日志。
- 正式页展示逻辑在 `assets/js/quant-main.js`。
- 若 payload 参数展示异常，优先检查 `quant_contract.py` 和 `update_report.py` 的 helper 测试。

---

## 6. 长任务规则

### 6.1 使用统一优化器 `quant_optimizer.py`

推荐使用统一优化器代替手工 sweep 脚本。支持三种搜索策略：

```bash
# 网格搜索（小空间穷举）
python scripts/quant_optimizer.py --preset preset2 --strategy grid \
  --params "w1=30,40,50 w3=30,40,50 score_band=0,1,2,3" --periods 1Y,3Y

# 随机搜索（大空间探索）
python scripts/quant_optimizer.py --preset preset2 --strategy random \
  --n-trials 200 --seed 42 --periods 1Y,3Y,6Y

# 贝叶斯优化（智能搜索，需 optuna）
python scripts/quant_optimizer.py --preset preset2 --strategy bayesian \
  --n-trials 100 --auto-bounds --periods 1Y,3Y,6Y

# 续跑
python scripts/quant_optimizer.py ... --resume
```

输出目录：`research/params/{preset}-{date}/`，含 `results.json`、`report.md`、`checkpoint.json`、`log.txt`。

参数空间由 `scripts/quant_contract.py` 的 `PARAM_BOUNDS` 统一定义，`--auto-bounds` 从 preset 当前值自动推导搜索范围。

### 6.2 后台运行（推荐）

```powershell
Start-Process -FilePath "python" `
  -ArgumentList "scripts\quant_optimizer.py --preset preset2 --strategy bayesian --n-trials 150 --auto-bounds --periods 1Y,3Y,6Y" `
  -WorkingDirectory "C:\Users\julentan\StockMarket\.claude\skills\etf-report"
```

完成后检查 `research/params/{preset}-{date}/report.md` 查看结论。

### 6.3 旧式批量搜索注意事项（仅用于兼容旧脚本）

- 每批组合数不要太大。
- 每个 combo 及时写 checkpoint。
- 输出 CSV/JSON 到 `data/param_search/` 或对应 `research/` 目录。
- 跑完后把结论写入 `research/params/README.md` 或对应研究目录。

---

## 7. 故障排查

| 现象 | 先查 | 处理 |
|---|---|---|
| Tuner 页面打不开 | `/api/data_status` / 端口 5179 | `python scripts/kill_tuner.py` 后重启 |
| 页面一直“正在加载量化数据” | Tuner 控制台 / `data/quant/*.csv` | 检查 CSV 是否存在，必要时跑 `quant_data_fetcher.py` |
| 参数契约显示 unavailable | `/api/param_schema` | 检查 `quant_contract.py` 和 Tuner 后端日志 |
| 回测收益突然变化 | `execution_timing` / preset diff / consistency check | 跑三个 preset 的 `quant_consistency_check.py` |
| Tuner 与 CLI 结果不一致 | `quant_contract.py` / `quant_backtest.py` | 先修一致性，禁止继续调参 |
| Save to YAML 后页面没变 | `/api/presets` / `config/quant_universe.yaml` | 刷新页面或重启 Tuner |
| 数据日期旧 | `/api/data_status` 的 `csvLatestDate` | 跑 `python scripts/quant_data_fetcher.py` |
| 腾讯 API 被封 | `quant_data_fetcher.py` 输出 | 减少请求，等待 24-48h，避免 `--full` |
| 正式页量化为空 | `assets/js/quant_payload.js` / update_report 日志 | 启动 Tuner 后重跑 update_report 或单独生成 payload |

---

## 8. 运维检查清单

### 改参数后

```bash
python -m pytest tests/test_quant_contract.py
python scripts/quant_consistency_check.py --preset preset2 --start 2025-01-01 --end 2026-05-19
```

### 改成交口径 / 调仓逻辑后

```bash
python -m pytest tests/test_quant_backtest_execution.py tests/test_quant_consistency.py
python scripts/quant_consistency_check.py --preset preset1 --start 2025-01-01 --end 2026-05-19
python scripts/quant_consistency_check.py --preset preset2 --start 2025-01-01 --end 2026-05-19
python scripts/quant_consistency_check.py --preset preset3 --start 2025-01-01 --end 2026-05-19
```

### 改正式页 payload 后

```bash
python -m pytest tests/test_update_report.py -k "quant_preset_params or quant_payload_config_section"
python -m py_compile scripts/update_report.py scripts/quant_contract.py
```

### 改数据源后

```bash
python scripts/quant_data_fetcher.py --code 512400
python scripts/quant_tuner.py
# 打开 http://localhost:5179/api/data_status
```
