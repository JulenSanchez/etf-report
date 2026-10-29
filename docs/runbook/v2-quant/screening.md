# ETF 候选筛选流程

> **触发词**: 用户说“筛选 ETF”。本文只负责候选发现；确认入池后进入 `docs/runbook/v2-quant/pool-change.md`。

## 输入

- 用户给出的方向：行业、主题、宽基、跨境、商品、风格等。
- 当前 universe：`config/quant_universe.yaml`。
- 筛选脚本：`scripts/scan_etf_universe.py`。
- 成交额来源：历史日线（`fund_etf_hist_sina`）取「最近已结束交易日」的收盘成交额，日期由 `latest_allowed_close_date` 判定，与运行时刻解耦（盘中/盘后均可跑）。缓存按 `_meta.as_of` 日期自动刷新。

## 执行

```bash
python scripts/scan_etf_universe.py --debug
```

若用户指定方向，优先用脚本参数或筛选结果中的字段缩小候选；不要直接改 `config/quant_universe.yaml`。

## 输出

- 候选表 / Excel / debug 摘要。
- 每个候选至少要能说明：代码、名称、市场、类型、规模/流动性、上市时长、与当前池子的关系。

## 审阅规则

> **AI 必须暂停**: 以下 5 条审查由 AI 输出分析结果，**最终决策由用户确认**。

| # | 规则 | AI 自动化 | 阈值 |
|---|------|----------|------|
| 1 | 与现有 ETF 重复暴露过高 | 计算 Jaccard > 0.5 → 标记"重复" | > 0.5 |
| 2 | 足够历史数据 | 检查 `history_days` 列 | ≥ 250 天 |
| 3 | 足够成交额/规模 | 检查 `amount_yi` 和 `aum_yi` 列 | 日均成交 > 2000 万 |
| 4 | QDII/商品/特殊策略 | 检查 `qdii` 字段和 sector | 标记"需额外审核" |
| 5 | 短名清晰 | AI 建议短名（去公司后缀），展示给用户 | 用户确认 |

## 交接到换池

用户确认候选后，进入：

```text
docs/runbook/v2-quant/pool-change.md
```

筛选流程不负责提交、发布。

## 最小验证

```bash
python scripts/scan_etf_universe.py --debug
```

验证通过标准：

- 脚本退出码为 0。
- 候选结果非空或明确说明无候选。
- 不读取或修改 `data/quant/`。
- 不修改 `config/quant_universe.yaml`。

## 已知陷阱

| # | 陷阱 | 表现 | 规则 |
|---|------|------|------|
| 1 | 当日 bar 滞后 | `fund_etf_hist_sina` 盘后可能尚未包含「今天」的 bar，最新数据停在上一交易日 | 取数用 `date <= latest_allowed_close_date()` 的最后一行兜底，不假设当天 bar 一定存在 |
| 2 | 不能并发取数 | `fund_etf_hist_sina` 内部用 `py_mini_racer`（V8），`MiniRacer()` 初始化非线程安全，并发会崩溃（`IsConfigurablePoolInitialized`） | 顺序取数，不用线程池 |
| 3 | 上市日期占位值 | 缓存中大量 ETF 标注为 1 月 1 日 / 6 月 1 日——均为缺失数据的占位符 | 上市日期不能用于计算，只用于展示。数据行数以缓存 CSV 或 API 实际返回为准 |
| 4 | 缓存值聚簇检查 | 某个数值（如 1024）出现频率异常高 | 每次运行后抽查缓存分布。若某值占比 >20%，排查 API 响应上限 |
