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
| 参数优化 | `docs/runbook/v2-quant/optimization.md` | 人类说"优化 <preset>"拉起，AI 自检→搜索→分析器→报告 |

## 故障排查索引

| 症状 | 优先看 |
|---|---|
| Tuner 白屏 / API 报错 | `docs/runbook/v2-quant/tuner.md` |
| CSV 缺失 / 数据不新 | `docs/runbook/v2-quant/data-fetch.md` |
| 某 ETF 净值异常跳变（拆股） | `docs/runbook/v2-quant/tuner.md` → 拆股自愈流程 |
| preclose push 失败 | `docs/runbook/v2-quant/daily-automation.md` |
| ETF 池变更后回测异常 | `docs/runbook/v2-quant/pool-change.md` |
| 正式页量化为空 | `docs/runbook/v1-report.md` |

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
