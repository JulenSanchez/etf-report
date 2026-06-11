# 正式页报告 — 运维手册

> v1.0 产品线：6 支 ETF 的 K 线图表、实时行情、成分股、宏观分析。感性信息。
> 量化推送（v2.0）见 `QUANT_RUNBOOK.md`。

## 一、每日自动化

### 定时任务

| 时间 | 任务名 | 脚本 | 做什么 |
|------|--------|------|--------|
| 16:00 | `etf报告发布` | `daily_report.bat` | 拉数据 → 生成报告 → GitHub Pages → 微信通知 |

### 数据流

```
新浪 getKLineData → fix_ma_and_benchmark.py → data/etf_full_kline_data.json
新浪 hq.sinajs.cn → realtime_data_updater.py → data/etf_realtime_data.json
                                ↓
                    update_report.py --publish
                                ↓
                    index.html (+ quant_payload.js*)
                                ↓
                    GitHub Pages (julensanchez.github.io/etf-report)
```

\* 量化板块数据来自 `update_report.py` 内部调用 `run_backtest()`，读取 `data/quant/*.csv`（45 支）。CSV 由 15:15 的盘后数据任务刷新（见 `QUANT_RUNBOOK.md`）。

### 容错

- **非交易日**：`daily_report.bat` 内置交易日检测，周末/假期自动跳过
- **数据不是最新**：脚本先跑一次 `quant_data_fetcher.py` 补拉当天数据再生成报告
- **GitHub Pages 推送失败**：检查 SSH 密钥 → `ssh -T git@github.com`

---

## 二、手动执行

```bash
# 开发模式（仅生成本地报告，不发布）
python scripts/update_report.py

# 发布模式（生成 + GitHub Pages + 微信通知）
python scripts/update_report.py --publish
```

### 8 步流程

| Step | 内容 | 耗时 |
|------|------|------|
| 1 | 份额变动识别 + 拉取 6 支 ETF 日线（新浪 getKLineData）→ 清洗 → 重建周线 + MA | ~3-5s |
| 2 | 获取沪深 300 基准指数 | ~2-3s |
| 3 | 获取实时行情 + 成分股涨跌幅（新浪 hq.sinajs.cn）| ~2-3s |
| 4 | 生成 index.html（注入 K 线数据 + 量化 payload） | ~0.8s |
| 5 | 健康检查（26 项） | ~0.8s |
| 6-7 | 企微通知（发布模式） | ~1-2s |
| 8 | GitHub Pages 部署（发布模式） | ~2-3s |

---

## 三、GitHub Pages

源码仓的 `main` 分支直接服务 GitHub Pages。`update_report.py --publish` 会更新根目录的 `index.html` 并提交到源码仓。非交易日生成的数据正常显示（日期滞后，不视为异常）。

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
powershell -ExecutionPolicy Bypass -File batchfiles\setup_report_task.ps1
```

---

## 常见问题

| 问题 | 排查 |
|------|------|
| 数据为空 | 检查 config.yaml ETF 代码；API 限流等 5 分钟重试 |
| 图表不显示 | 检查 `data/etf_full_kline_data.json` 数据格式 |
| 健康检查 FAIL | 查看具体失败项；少量 WARN 通常不影响 |
| 发布失败 | 检查 `config/secrets.yaml`、SSH：`ssh -T git@github.com` |
| 量化板块显示"建设中" | 量化回测仅在开发环境可用，见 `QUANT_RUNBOOK.md` |

---

## 相关文档

- 系统架构：`DESIGN.md`
- 量化运维：`runbooks/QUANT_RUNBOOK.md`
- 代码审计：`runbooks/AUDIT_RUNBOOK.md`
- 发布门禁：`runbooks/RELEASE_RUNBOOK.md`
