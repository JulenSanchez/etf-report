# ETF 报告生成技能 (etf-report)

自动分析与生成 6 支 ETF 的投资分析报告（K线、均线、实时行情、成分股、宏观分析）。
数据+模板分离架构，100% 保持原始 HTML 样式一致。

## 触发词

"更新ETF报告"、"生成ETF分析报告"、"刷新投资数据"、"看看今天的ETF"

## 这个技能负责什么

它的核心职责只有三类：

- **更新报告**：抓取 ETF 数据、生成并更新根目录 `index.html`
- **调整配置**：修改 ETF 池、基准、解释层内容、发布开关等配置
- **接入发布**：把生成结果接到企微通知、GitHub Pages 或你自己的发布链路

## Agent 首读顺序

建议按下面顺序理解：

1. `SKILL.md`：先判断这个技能是否匹配当前任务。
2. `README.md`：如果要真正运行、改配置、接发布，转到这里。
3. `WORKFLOW.md`：如果要排障、核对步骤、做验证，再往下读这里。
4. `config/*.yaml` 和 `scripts/*.py`：最后进入事实源与实现。

如果当前工作区**额外存在** `CONTRIBUTING.md`，说明你不是在“使用这个技能”，而是在“维护这个技能本体”；此时开发任务应优先读 `CONTRIBUTING.md`。

### 快捷提示词

- "更新ETF报告" / "跑一下" → 运行主流程
- "改配置" / "换 ETF" / "换标的" → 先读 `README.md` 的配置部分
- "发布" / "接发布链路" → 先读 `README.md` 的发布准备，再查 `scripts/notifier.py` / `scripts/deployer.py`
- "做个健康检查" / "哪里有问题" → 先读 `WORKFLOW.md`
- "继续开发这个技能" / "维护技能本体" → 如果存在，先读 `CONTRIBUTING.md`

## 项目导航

| 我需要 | 去哪里 |
|--------|--------|
| 理解完整工作流程 | `WORKFLOW.md` |
| 理解系统架构设计 | `DESIGN.md` |
| 查 AKShare / 外部数据源接入参考 | `docs/AKSHARE_SCRIPTING_REFERENCE.md` |
| 查 AKShare 候选接口清单 | `docs/AKSHARE_CANDIDATE_INTERFACES.md` |
| 做 ETF 换标的 / 替换流程 | `docs/ETF_REPLACEMENT_CHECKLIST.md` |
| 配置与运行入口 | `README.md` |
| 查配置参数 | `config/config.example.yaml` + `config/holdings.yaml`（`config/config.yaml` 为本地覆盖） |
| 接企微通知 / 发布实现 | `scripts/notifier.py` + `scripts/deployer.py` |
| 在线报告 | https://julensanchez.github.io/etf-report/ |
| 本地预览 | 根目录 `index.html`（用 `file://` 打开） |



## 项目结构

```
etf-report/
├── scripts/        ← Python 脚本（update_report.py 为主控）
├── config/         ← 公开模板 + 本地覆盖（example / holdings / secrets 模板）
├── docs/           ← 参考文档
├── tests/          ← 回归测试
├── data/           ← 运行时数据（不提交）
├── logs/           ← 结构化执行日志（不提交）
├── .backup/        ← 事务回滚快照（不提交）
├── _working/       ← 一次性人工排查输出（不提交）
├── outputs/        ← 兼容/手工导出临时区（默认保持空）
├── README.md       ← 外部安装与快速开始入口
├── SKILL.md        ← 本文件
├── WORKFLOW.md     ← 执行手册
├── DESIGN.md       ← 架构设计
├── requirements.txt← Python 依赖清单
└── index.html      ← 发布产物（脚本生成）
```


### 目录卫生约定

- 根目录只保留源码、文档和主报告 `index.html`，不要落 `_pytest*.txt`、`_update_report*.txt`、`*.bak*` 这类一次性文件。
- 运行型产物只留在 `data/`、`logs/`、`.backup/`。
- 一次性人工排查输出统一放 `_working/`；需要长期复用的样本请放 `tests/fixtures/`。
