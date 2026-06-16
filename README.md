# etf-report

ETF 正式报告页 + 量化回测实验室。

在线报告：https://julensanchez.github.io/etf-report/

## Quick Start

```bash
git clone https://github.com/JulenSanchez/etf-report.git
cd etf-report
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
```

## 常用命令

```bash
# 生成/更新正式页报告
python scripts/update_report.py
python scripts/report_site/update_report.py

# 健康检查
python scripts/health_check.py
python scripts/report_site/health_check.py

# 启动量化 Tuner
python scripts/quant_tuner.py
python scripts/quant_lab/quant_tuner.py
# 浏览器打开 http://localhost:5179

# 生成正式页量化 payload
python scripts/quant_build_payload.py
python scripts/quant_lab/quant_build_payload.py

# 测试
pytest tests -q
```

## GitHub Pages 发布

当前 GitHub Pages 直接服务源码仓 `main` 分支的根目录发布面：

- `index.html`
- `assets/js/runtime_payload.js`
- `assets/js/quant_payload.js`
- `assets/js/quant-main.js`
- `assets/js/report-main.js`
- `assets/js/chart-lifecycle.js`
- `assets/js/debug-toolbar.js`

因此本轮项目化改造仍保留根目录 `index.html` 和 `assets/`，避免远端 Pages 断站。

发布前先读：`docs/ops/release.md`。

## 目录结构

```text
etf-report/
├── index.html                 # GitHub Pages 正式页发布面
├── assets/                    # 正式页 CSS/JS 与 payload
├── config/                    # 项目配置与本地 secrets 模板
├── scripts/                   # 兼容旧入口 + shared 脚本
│   ├── report_site/           # v1.0 正式页入口 wrapper
│   └── quant_lab/             # v2/v3 量化入口 wrapper
├── src/etf_report/core/       # 共享项目路径等基础模块
├── tests/                     # 回归测试
├── docs/
│   ├── ai/                    # AI 协作说明与 legacy skill 配置
│   ├── ops/                   # report / quant / release / audit 运维文档
│   └── architecture/          # 架构设计与子系统文档
├── research/                  # 研究记录与 promotion 证据
├── plans/                     # 历史需求治理材料
├── data/                      # ignored，运行数据与缓存
├── logs/                      # ignored，运行日志
└── requirements.txt
```

## 配置

| 文件 | 说明 |
|---|---|
| `config/config.example.yaml` | 公开配置模板，clone 后默认可用 |
| `config/config.yaml` | 本地覆盖配置 |
| `config/secrets.example.yaml` | 敏感配置模板 |
| `config/secrets.yaml` | 本地敏感配置，不提交 |
| `config/quant_universe.yaml` | 量化池、因子、preset 事实源 |

## 文档入口

| 文档 | 内容 |
|---|---|
| `docs/architecture.md` | 系统架构总览 |
| `docs/ops/report.md` | 正式页报告生成与发布链路 |
| `docs/ops/quant/overview.md` | 量化系统总览与运维索引 |
| `docs/ops/release.md` | GitHub Pages 发布门禁 |
| `docs/ops/stable.md` | stable 仓库与计划任务运维 |
| `docs/ops/audit.md` | 项目审计方法 |
| `docs/ai/AGENT_GUIDE.md` | AI 协作约定 |
| `research/README.md` | 研究索引 |

## 运行产物

`data/`、`logs/`、`outputs/`、`_working/` 是本地运行产物或临时目录，默认不提交。测试所需的小样本应放入 `tests/fixtures/`。
