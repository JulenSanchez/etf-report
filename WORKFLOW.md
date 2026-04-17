# ETF 报告生成工作流 — 执行手册

## 快速开始

```bash
# 开发模式（默认）：步骤 1-6，~11 秒
python scripts/update_report.py

# 发布模式：步骤 1-8，~15 秒（含企微通知 + GitHub Pages）
python scripts/update_report.py --publish
```

## 执行步骤

### Step 1: 主流程内嵌份额变动识别并清洗 K 线数据（~3-5s）

主流程会先按当前图表窗口自动同步基金拆分/折算事件，并输出结构化事件文件 `data/corporate_action_events.json`。
随后从新浪财经 API 获取 6 支 ETF 的日线源数据，立即执行数据清洗（优先消费自动识别事件，手工配置作为兼容兜底），再基于清洗后的日线重建周线并计算 MA5/MA20/MA50（已预热 19 天）。
输出：`data/etf_full_kline_data.json`



### Step 2: 获取基准指数（~2-3s）

获取沪深 300 基准指数用于对比分析，写入 K 线数据的 `benchmark` 字段。

### Step 3: 获取实时行情（~2-3s）

获取当日 ETF 涨跌幅、成交量、成分股涨跌幅。
成分股列表来自 `config/holdings.yaml`。
输出：`data/etf_realtime_data.json`

### Step 4: 生成 HTML 报告（~0.8s）

将数据注入到根目录 `index.html` 的 JavaScript 对象中。100% 样式保证。
周末/节假日数据为空属正常行为。

### Step 5: 健康检查（~0.8s）

26 项自动检查（文件完整性、数据有效性、脚本依赖、HTML 结构、工作流逻辑、系统配置，含解释层鲜度检查）。
主流程内会把结果汇总到终端与执行日志；如需单独查看明细，可运行 `python scripts/health_check.py` 或 `python scripts/health_check.py --json`。

### Step 6-7: 企微通知（发布模式，~1-2s）

推送报告摘要到企业微信。自动重试 3 次。

### Step 8: GitHub Pages 部署（发布模式，~2-3s）

如果 GitHub Pages 直接服务当前源码仓分支，发布流程会先更新技能根目录的 `index.html`，再只把当天这一个文件提交到源码仓；只有在 `pages_repo_root` 指向**不同 remote / 不同分支**的独立 Pages 仓时，才会额外把这份 `index.html` 复制过去并执行 git add/commit/push。需配置 SSH 密钥。




## 常见问题

| 问题 | 排查 |
|------|------|
| 数据为空 | 检查 `config/config.example.yaml` 或本地 `config/config.yaml` 中的 ETF 代码，API 限流则等 5 分钟重试 |
| 图表不显示 | 检查 `data/etf_full_kline_data.json` 数据格式 |
| 健康检查出现 FAIL | 查看具体失败项；若只有少量 WARN，通常仍不影响报告生成 |
| 发布失败 | 先检查本地 `config/config.yaml` 的 `publish` 配置，再检查 `config/secrets.yaml`、SSH：`ssh -T git@github.com` |
| MA50 为 null | 正常，前 50 天预热期不够 |


## 目录约定

- `data/`：日更运行数据与运行时载荷。
- `logs/`：结构化 JSONL 日志。
- `.backup/`：事务回滚快照。
- `_working/`：一次性人工排查输出。
- `tests/fixtures/`：需要长期复用的样本。
- 根目录不保留 `_pytest*.txt`、`_update_report*.txt`、`_detail_mismatch*.txt`、`*.bak*`。

## 项目审计

```bash
python scripts/audit_project.py --quick   # 10 秒，结构 + 安全
python scripts/audit_project.py --full    # 30 秒，4 个模块
```
