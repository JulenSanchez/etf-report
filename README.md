# ETF 报告生成工作流

自动分析与生成 6 支 ETF 的投资分析报告。

![Version](https://img.shields.io/badge/version-v2.5.1-blue)
![License](https://img.shields.io/badge/license-MIT-green)

**在线报告**：[查看最新报告](https://julensanchez.github.io/etf-report/)

## 快速开始

```bash
git clone https://github.com/JulenSanchez/etf-report.git
cd etf-report
pip install -r requirements.txt
python scripts/update_report.py
```

clone 后无需额外配置即可运行——默认读取 `config/config.example.yaml`。

## 目录结构

```
etf-report/
├── index.html              ← 报告页面（本地预览 / 发布产物）
├── assets/
│   ├── css/report.css      ← 报告样式
│   └── js/
│       ├── report-main.js  ← 报告主逻辑
│       └── chart-lifecycle.js ← 图表生命周期
├── config/
│   ├── config.example.yaml ← 公开配置模板（默认生效）
│   ├── secrets.example.yaml← 敏感配置模板
│   ├── holdings.yaml       ← 成分股事实源
│   ├── editorial_content.yaml ← 解释层内容
│   ├── editorial_sources.yaml ← 编辑源配置
│   └── compliance_rules.yaml  ← 合规规则
├── scripts/                ← Python 主流程与辅助脚本（15 个）
├── tests/                  ← 回归测试（14 个）
├── docs/                   ← 参考文档
│   ├── AKSHARE_SCRIPTING_REFERENCE.md
│   ├── AKSHARE_CANDIDATE_INTERFACES.md
│   ├── DAILY_UPDATE_PARAMETERS.md
│   ├── ETF_REPLACEMENT_CHECKLIST.md
│   ├── HEALTH_CHECK_KNOWN_ISSUES.md
│   └── HEALTH_CHECK_USAGE.md
├── .github/workflows/      ← CI 配置
├── SKILL.md                ← AI 技能描述卡
├── README.md               ← 本文件
├── WORKFLOW.md             ← 执行手册
├── DESIGN.md               ← 架构设计
└── requirements.txt        ← Python 依赖
```

运行后会在本地生成以下目录（不提交到 Git）：

| 目录 | 内容 |
|------|------|
| `data/` | K 线数据、实时行情、运行时载荷 |
| `logs/` | 每日结构化运行日志 |

## 配置说明

| 文件 | 说明 |
|------|------|
| `config/config.example.yaml` | 公开模板，clone 后默认生效 |
| `config/config.yaml` | 本地覆盖配置（从 example 复制后修改，不提交） |
| `config/secrets.example.yaml` | 敏感配置模板 |
| `config/secrets.yaml` | 本地敏感配置（企微 webhook 等，不提交） |
| `config/holdings.yaml` | 成分股事实源 |
| `config/editorial_content.yaml` | 解释层文案 |

优先级：环境变量 > 命令行参数 > `config.yaml` > `config.example.yaml` > 代码默认值。

## 运行与发布

```bash
# 开发模式（默认）
python scripts/update_report.py

# 发布模式（需先配置 secrets）
python scripts/update_report.py --publish
```

`--publish` 会先更新本地 `index.html`，再将报告推送到 GitHub Pages 并发送企微通知。

## 推荐使用顺序

1. 安装依赖：`pip install -r requirements.txt`
2. 先直接运行一次：`python scripts/update_report.py`
3. 需要自定义时，复制 `config/config.example.yaml` → `config/config.yaml` 并修改
4. 需要发布时，补 `config/secrets.yaml` 并执行 `--publish`

## 进一步说明

| 文档 | 内容 |
|------|------|
| [WORKFLOW.md](WORKFLOW.md) | 详细执行步骤、排障、验证 |
| [DESIGN.md](DESIGN.md) | 架构设计与模块依赖 |
| [SKILL.md](SKILL.md) | AI 技能描述与触发词 |
| [docs/](docs/) | AKShare 参考、ETF 替换清单、健康检查说明 |

建议在交易日收盘后（15:00 之后）执行更新。

---

**版本**: v2.5.1 | **最后更新**: 2026-04-22
