# ETF 报告生成工作流

自动分析与生成 6 支 ETF 的投资分析报告。

![Version](https://img.shields.io/badge/version-v3.1.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)

**在线报告**：[查看最新报告](https://julensanchez.github.io/etf-report/)

## 快速开始

### 1. 环境准备

需要 Python 3.10+。推荐使用虚拟环境：

```bash
git clone https://github.com/JulenSanchez/etf-report.git
cd etf-report
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
```

**依赖清单**（7 个第三方包）：

| 包名 | pip 安装名 | 用途 |
|------|-----------|------|
| numpy | `numpy` | 数值计算（因子打分、回测） |
| pandas | `pandas` | 数据处理（K线、回测引擎） |
| PyYAML | `pyyaml` | YAML 配置读写 |
| requests | `requests` | HTTP 请求（腾讯K线API、数据拉取） |
| Flask | `flask` | Tuner 本地 Web 服务 |
| BeautifulSoup4 | `beautifulsoup4` | HTML 解析（编辑源抓取） |
| AKShare | `akshare` | 金融数据接口（沪深300日线、ETF分红、指数估值等） |

> 注意：`pyyaml` 的 import 名是 `yaml`，`beautifulsoup4` 的 import 名是 `bs4`。

### 2. 运行

```bash
# 生成报告
python scripts/update_report.py

# 启动 Tuner（量化回测调试工具）
python scripts/quant_tuner.py
# 浏览器打开 http://localhost:5179
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
├── docs/                   ← 参考文档（扁平结构）
│   ├── 01-数据源与工具生态.md
│   ├── 02-外部数据合规入门.md
│   ├── 03-A股行业分类体系对比.md
│   ├── 04-ETF估值方法论.md
│   ├── 05-量化估值因子入门.md
│   ├── 06-技术分析简介.md
│   ├── 07-quant-methodology.md
│   ├── AKSHARE_CANDIDATE_INTERFACES.md
│   ├── AKSHARE_SCRIPTING_REFERENCE.md
│   ├── DAILY_UPDATE_PARAMETERS.md
│   ├── ETF_REPLACEMENT_CHECKLIST.md
│   ├── HEALTH_CHECK_USAGE.md
│   └── HEALTH_CHECK_KNOWN_ISSUES.md
├── research/               ← 量化调研归档（按 REQ ID 组织，含索引）
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

**持久化目录**（提交到 Git）：

| 目录 | 内容 |
|------|------|
| `research/` | 量化调研归档（报告 + 实验数据），按 REQ ID 组织，索引见 `research/README.md` |

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
| [docs/](docs/) | 文档（通识知识、运维手册、工具参考） |

建议在交易日收盘后（15:00 之后）执行更新。

## 开发工具

### Quant Tuner（量化调参面板）

本地 Flask 服务，提供可视化滑块调参 + 一键回测，用于调优量化策略参数。

```bash
python scripts/quant_tuner.py
# → http://localhost:5179
```

**注意**：此工具必须通过 `http://localhost` 访问（需要后端计算），不走 `file://` 协议。

| 特性 | 说明 |
|------|------|
| 协议 | `http://localhost:5179`（Flask 本地服务） |
| 定位 | 开发调试工具，不纳入 `index.html` 静态页面 |
| Git | 正常提交，属于项目 feature（`scripts/quant_tuner.py`） |
| 数据 | 启动时一次性预加载 25 支 ETF 历史数据 + F4 估值分数，回测过程无网络请求 |
| 可调参数 | 因子权重(F1-F4) / 偏好加成 / 信心函数(类型/死区/满配) / 仓位控制(持仓数/步长) / 因子周期(EMA/RSI/量比) / 标的池筛选 |
| 保存 | "保存参数"按钮直接写回 `config/quant_universe.yaml` |

调参完成后：关闭 Flask → 执行 `python scripts/quant_build_payload.py` 重新生成正式 payload。

---

**版本**: v2.5.1 | **最后更新**: 2026-04-22
