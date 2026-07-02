# 正式页报告 — 运维手册

> v1.0 产品线：6 支 ETF 的 K 线图表、实时行情、成分股、宏观分析。感性信息。
> 量化推送（v2.0）见 `docs/runbook/v2-quant/overview.md`。

## 一、每日自动化

计划任务的注册、检查和 stable 仓运维统一见 `docs/runbook/stable.md`。本文只说明正式页生成链路。

### 数据流

```
新浪 getKLineData → fix_ma_and_benchmark.py → data/etf_full_kline_data.json
新浪 hq.sinajs.cn → realtime_data_updater.py → data/etf_realtime_data.json
                                ↓
                    update_report.py
                                ↓
                    index.html (+ quant_payload.js*)
                                ↓
                    GitHub Pages (julensanchez.github.io/etf-report)
```

\* 量化板块数据来自 `update_report.py` 内部调用 `run_backtest()`，读取 `data/quant/*.csv`。CSV 由 15:15 的盘后数据任务刷新（见 `docs/runbook/v2-quant/overview.md`）。

### 容错

- **非交易日**：`daily_report.bat` 内置交易日检测，周末/假期自动跳过
- **数据不是最新**：脚本先跑一次 `quant_data_fetcher.py` 补拉当天数据再生成报告
- **GitHub Pages 推送失败**：检查 SSH 密钥 → `ssh -T git@github.com`

---

## 二、手动执行

> **AI 执行**: `python scripts/update_report.py` 是唯一入口。内部 8 步流程（拉 K 线、取实时行情、抓 editorial、更新量化数据、写 payload）对 AI 透明——AI 只关心最终输出。

```bash
python scripts/update_report.py
```
→ **预期**: EXIT=0。stdout 含 `[OK]` 标记，健康检查全部 passed（具体数量以脚本输出为准）。`index.html` 和 `assets/js/runtime_payload.js` 更新为当日日期。量化板块（如有 `quant_payload.js`）同步刷新。执行时间约 2-3 分钟（含 editorial 抓取）。

发布必须进入 `docs/runbook/release.md` 的 Phase 0-8；不要从本文直接执行 `--publish`。

### 8 步流程

| Step | 内容 | 耗时 |
|------|------|------|
| 1 | 份额变动识别 + 拉取 6 支 ETF 日线（新浪 getKLineData）→ 清洗 → 重建周线 + MA | ~3-5s |
| 2 | 获取沪深 300 基准指数 | ~2-3s |
| 3 | 获取实时行情 + 成分股涨跌幅（新浪 hq.sinajs.cn）| ~2-3s |
| 4 | 生成 index.html（注入 K 线数据 + 量化 payload） | ~0.8s |
| 5 | 健康检查（全量，数量以脚本输出为准） | ~0.8s |
| 6-7 | 企微通知（发布模式） | ~1-2s |
| 8 | GitHub Pages 部署（发布模式） | ~2-3s |

---

## 三、GitHub Pages

源码仓的 `main` 分支直接服务 GitHub Pages。发布、提交、推送统一按 `docs/runbook/release.md` 执行。非交易日生成的数据正常显示（日期滞后，不视为异常）。

---

## 四、新电脑初始化

```powershell
# 1. Clone
git clone https://github.com/JulenSanchez/etf-report.git
cd etf-report

# 2. 配置 secrets
# 复制 config/secrets.example.yaml → config/secrets.yaml，填入 Server酱 sendkey

# 3. 拉初始数据
python scripts/quant_data_fetcher.py --full

# 4. 安装定时任务
# 详见 docs/runbook/stable.md
powershell -ExecutionPolicy Bypass -File batchfiles\setup_report_task.ps1
```

---

## 常见问题

| 症状 | 可能原因 | 检查 |
|------|---------|------|
| 数据为空 | config.yaml ETF 代码错误；API 限流 | 等 5 分钟重试 |
| 图表不显示 | `data/etf_full_kline_data.json` 格式异常 | 检查 JSON 结构 |
| 健康检查 FAIL | 看具体失败项 | 少量 WARN 通常不影响 |
| 发布失败 | SSH / secrets 问题 | `ssh -T git@github.com` |
| 量化板块为空 | `quant_payload.js` 未生成或字段缺失 | 运行 `python scripts/quant_build_payload.py`，再看 `docs/runbook/v2-quant/overview.md` |
| 推送内容 ETF 显示代码非中文名 | `preclose_push.py` 的 name map 未更新 | 确认 `config/quant_universe.yaml` 有 `name` 字段 |
| 定时任务跑了 stable 目录但结果含新 ETF | stable/main 双源分裂：Tuner 进程跑在另一仓库 | `netstat -ano \| findstr 5179`，确认进程路径 |
| preclose_push 盘中数据不刷新 | 盘中缓存规则：15:10 前不拉取收盘数据 | 检查 `history_days.json` 时间戳；`--force-refresh` 拒绝 pre-close |
| 发布后页面日期滞后 | 非交易日数据正常显示 | 不视为异常 |

---

## 相关文档

- 系统架构：`docs/design/overview.md`
- 量化运维：`docs/runbook/v2-quant/overview.md`
- 代码审计：`docs/runbook/audit.md`
- 发布门禁：`docs/runbook/release.md`
