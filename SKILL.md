# ETF 报告生成技能 (etf-report)

自动分析与生成 6 支 ETF 的投资分析报告（K线、均线、实时行情、成分股、宏观分析）。
数据+模板分离架构，100% 保持原始 HTML 样式一致。

## 触发词

"更新ETF报告"、"生成ETF分析报告"、"刷新投资数据"、"看看今天的ETF"、"调参"、"量化调参"、"quant tuner"、"回测调试"

## 这个技能做什么

三类核心能力：

- **更新报告**：抓取 ETF 数据、生成并更新 `index.html`
- **调整配置**：修改 ETF 池、基准、解释层内容、发布开关等配置
- **接入发布**：把生成结果接到企微通知、GitHub Pages

## Agent 首读顺序

1. **`SKILL.md`**（本文件）：判断技能是否匹配当前任务
2. **`README.md`**：配置、运行、目录结构
3. **`WORKFLOW.md`**：排障、核对步骤、验证
4. **`DESIGN.md`**：架构设计与模块依赖
5. **`research/README.md`**：量化调研索引（按 REQ ID 查找历史调研产出）
6. **`config/*.yaml`** / **`scripts/*.py`**：进入事实源与实现

### 快捷提示词

| 用户说 | Agent 做 |
|--------|---------|
| "更新ETF报告" / "跑一下" | 运行 `python scripts/update_report.py` |
| "改配置" / "换 ETF" | 读 `README.md` 配置部分 |
| "发布" | 必须先读 `runbooks/RELEASE_RUNBOOK.md`（唯一门禁），勿直跳 README |
| "做个健康检查" | 读 `WORKFLOW.md` |
| "调参" / "量化调参" / "quant tuner" | 启动 `python scripts/quant_tuner.py` → http://localhost:5179 |
| "查看XX调研" / "后视镜调研" / "research" | 读 `research/README.md` 索引，定位对应 REQ 子目录 |

## 在线报告

https://julensanchez.github.io/etf-report/

## 数据抓取失败处置

运行 `update_report.py` 或量化管线时，若出现以下错误，按对应路径处置：

| 现象 | 可能原因 | AI 处置 |
|------|---------|---------|
| `ConnectionError` / `HTTPError 403/503` / `timeout` | 数据源被限流或 IP 封禁 | 告知用户当前数据源受限，建议等待 30 分钟后重试；不要反复重跑加剧封禁 |
| `AKShare` 相关 `Exception` / `KeyError` 找不到字段 | AKShare 接口变更或数据源下线 | 读 `WORKFLOW.md` 排障节；核查 `scripts/fix_ma_and_benchmark.py` 和 `realtime_data_updater.py` 的数据源调用 |
| 量化 CSV 相关 `No CSV data` / `FileNotFoundError` | `data/quant/` 为空（冷启动场景） | 运行 `python scripts/quant_tuner.py --auto` 触发冷启动（约 3-5 分钟），或手动 `python scripts/quant_data_fetcher.py --full` |
| 腾讯 fqkline `code: 1, msg: param error` / `HTTP 403` | 量化数据源被封 | 详见 `runbooks/QUANT_RUNBOOK.md` §3.6；核心对策：减少请求频率、换 IP、等待 24-48h 解封 |
| 脚本报错但不是上述类型 | 代码 bug 或环境问题 | 读完整报错栈，优先看最后一行 `caused by`；依赖缺失则 `pip install -r requirements.txt` |

**通用原则**：
- 数据源失败不等于代码 bug，先区分"网络/源问题"和"代码问题"再动手
- 上次成功的数据仍在本地缓存（`data/`），可用旧数据生成报告，告知用户数据日期可能不是最新
