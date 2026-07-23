# 量化运维总览

量化系统由数据层、回测引擎、Tuner、正式页 payload 和研究归档组成。本文件只保留入口和事实源索引；具体操作见同目录短文档。

## 系统边界

| 子系统 | 入口 | 职责 | 不负责 |
|---|---|---|---|
| 数据层 | `scripts/quant_data_fetcher.py` | 拉取 ETF K 线，维护 `data/quant/*.csv` | 解释策略、保存参数 |
| 回测引擎 | `scripts/quant_backtest.py` | 唯一回测计算核心，输出 NAV 与 signal history | Flask、HTML、用户交互 |
| Tuner | `scripts/quant_tuner.py` + `templates/tuner.html` | 本地交互调参、运行回测、保存 preset | 定义真实回测逻辑 |
| 正式页 payload | `scripts/update_report.py` / `scripts/quant_build_payload.py` | 生成静态量化结果供 `index.html` 渲染 | 交互调参 |
| 研究归档 | `research/` | 保存实验、证据、promotion 记录 | 当前参数事实源 |

## 当前架构

```text
config/quant_universe.yaml
  ├─ universe: ETF 池
  └─ presets: 当前策略参数

scripts/quant_data_fetcher.py
  └─ data/quant/*.csv

scripts/quant_backtest.py  ← 唯一回测引擎
  ├─ CLI 直接调用
  ├─ scripts/quant_tuner.py
  └─ scripts/update_report.py / quant_build_payload.py

assets/js/quant_payload.js
  └─ index.html + assets/js/quant-main.js
```

## 事实源优先级

| 问题 | 第一事实源 | 第二事实源 |
|---|---|---|
| 当前 ETF 池 / preset 参数 | `config/quant_universe.yaml` | `research/params/README.md` |
| 回测实际计算过程 | `scripts/quant_backtest.py` | `docs/design/backtest-engine.md` |
| Tuner API 与缓存 | `scripts/quant_tuner.py` | `docs/runbook/v2-quant/tuner.md` |
| 数据刷新和 CSV | `scripts/quant_data_fetcher.py` | `docs/runbook/v2-quant/data-fetch.md` |
| ETF 池变更 | `docs/runbook/v2-quant/pool-change.md` | `research/pool/README.md` |
| 正式页量化展示 | `assets/js/quant-main.js` | `docs/runbook/v1-report.md` |
| 日常自动化 / preclose push | `batchfiles/` + `scripts/preclose_push.py` | `docs/runbook/v2-quant/daily-automation.md` |

## 变更路由

| 变更类型 | 先读 | 最小验证 |
|---|---|---|
| 改因子 / 回测逻辑 | `docs/design/backtest-engine.md` | `python -m pytest tests/test_quant_* -q` |
| 改 Tuner 参数 | `docs/runbook/v2-quant/tuner.md` + `src/etf_report/core/quant_contract.py` | `python -m pytest tests/test_quant_contract.py -q` |
| 筛选 ETF | `docs/runbook/v2-quant/screening.md` | 生成候选表 + 人工审阅 |
| 改 ETF 池 | `docs/runbook/v2-quant/pool-change.md` | 逐支拉数 + 回测基线对比 |
| 改数据源 / CSV | `docs/runbook/v2-quant/data-fetch.md` | `python scripts/quant_data_fetcher.py --start <date> --end <date>` |
| 改正式页 payload | `docs/runbook/v1-report.md` | `python scripts/quant_build_payload.py` + HTML 验证 |
| 改 Tuner UI / 配色 | `docs/runbook/v2-quant/tuner.md` + `docs/design/tuner-ui.md` | 浏览器刷新，肉眼对比改前后 |
| 改日常推送 | `docs/runbook/v2-quant/daily-automation.md` | 检查计划任务 + dry-run/手动运行 |
| 参数优化 | `scripts/research_utils.py` + `docs/runbook/v2-quant/optimization.md` | sweep / 分组 TPE / `optimize_group()`，产出更新 YAML + `preset_metrics.json` |

## 故障排查索引

| 症状 | 优先看 |
|---|---|
| Tuner 白屏 / API 报错 | `docs/runbook/v2-quant/tuner.md` |
| CSV 缺失 / 数据不新 | `docs/runbook/v2-quant/data-fetch.md` |
| 某 ETF 净值异常跳变（拆股） | `docs/runbook/v2-quant/tuner.md` → 拆股修复用户流程（DM 面板 ⚠ → 手动修复） |
| preclose push 失败 | `docs/runbook/v2-quant/daily-automation.md` |
| ETF 池变更后回测异常 | `docs/runbook/v2-quant/pool-change.md` |
| 正式页量化为空 | `docs/runbook/v1-report.md` |
| 盘中 Tuner 信号与盘后不一致 / 牛熊误判 | 见下方"Tuner 与 CLI 数据路径差异" |

### Tuner 与 CLI 数据路径差异

**Tuner 盘中回测和 CLI 回测可以得出不同的信号——两者都可能正确，因为消费的数据不同。**

| | Tuner 盘中 | CLI / research_utils |
|---|---|---|
| ETF 日线 | `_get_daily_with_cache` = CSV + intraday 合并 | CSV only |
| 沪深300 MA 缓存 | `_build_ma_trend_cache`（含盘中实时价补丁） | 同函数，但无 intraday 触发补丁，纯 CSV |
| debug 输出文件 | `data/debug_tuner.json` | `data/debug_cli.json` |

**排障规则**：用户说"我 Tuner 看到了 X" → **X 是真的**。下一步是读 `debug_tuner.json` 找 Tuner 路径的根因，不是拿 CLI 结论反驳用户。CLI 结论只用于对照（"同数据不同结果"才是 bug），不是事实源。

盘中信号依赖 `intraday_cache` 内的数据新鲜度——如果 Tuner 启动后再没刷新过盘中数据，MA 信号会滞后一个周线窗口。刷新数据后再跑回测可消除滞后。

## 相关文档

- Tuner 运维：`docs/runbook/v2-quant/tuner.md`
- 数据刷新：`docs/runbook/v2-quant/data-fetch.md`
- ETF 筛选：`docs/runbook/v2-quant/screening.md`
- ETF 池变更：`docs/runbook/v2-quant/pool-change.md`
- 研究投产：`docs/runbook/v2-quant/preset-change.md`
- 每日自动化：`docs/runbook/v2-quant/daily-automation.md`
- 参数优化流程与报告：`docs/runbook/v2-quant/optimization.md`
- 回测引擎设计：`docs/design/backtest-engine.md`
- 默认策略管理：`docs/runbook/v2-quant/preset-change.md`
