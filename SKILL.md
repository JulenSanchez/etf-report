# ETF 报告生成技能 (etf-report)

自动分析与生成 6 支 ETF 的投资分析报告（K线、均线、实时行情、成分股、宏观分析）。
数据+模板分离架构，100% 保持原始 HTML 样式一致。

## 触发词

"更新ETF报告"、"生成ETF分析报告"、"刷新投资数据"、"看看今天的ETF"

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
5. **`config/*.yaml`** / **`scripts/*.py`**：进入事实源与实现

### 快捷提示词

| 用户说 | Agent 做 |
|--------|---------|
| "更新ETF报告" / "跑一下" | 运行 `python scripts/update_report.py` |
| "改配置" / "换 ETF" | 读 `README.md` 配置部分 |
| "发布" | 读 `README.md` 发布部分，再查 `scripts/deployer.py` |
| "做个健康检查" | 读 `WORKFLOW.md` |

## 在线报告

https://julensanchez.github.io/etf-report/
