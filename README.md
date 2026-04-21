# ETF 报告生成工作流

自动分析与生成 6 支 ETF 的投资分析报告。

![Version](https://img.shields.io/badge/version-v2.2.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## 📂 本地预览（默认）

遵循用户级规则 [`~/.codebuddy/rules/local-file-open.md`](../../../../../.codebuddy/rules/local-file-open.md)：HTML 一律用 `file://` 直开，不切 `http://localhost`。

本项目入口：`file:///c:/Users/julentan/CodeBuddy/StockMarket/.codebuddy/skills/etf-report/index.html`

## 📊 在线报告（发布产物）

[查看最新报告](https://julensanchez.github.io/etf-report/)

## 🚀 快速开始

```bash
git clone https://github.com/YOUR_USERNAME/etf-report.git
cd etf-report
pip install -r requirements.txt
python scripts/update_report.py
```

## ⚙️ 配置文件说明

- **`config/config.example.yaml`**：公开模板配置。默认直接读取它，所以 **clone 后不复制配置也能先跑主流程**。
- **`config/config.yaml`**：本地覆盖配置。需要改 ETF 池、API 参数、发布配置时，从 `config/config.example.yaml` 复制一份再修改。
- **`config/secrets.example.yaml`**：敏感配置模板。需要启用企微通知等敏感能力时，复制为 `config/secrets.yaml` 后在本地填写真实值。
- **`config/holdings.yaml`**：成分股事实源。
- **`config/editorial_content.yaml`**：解释层 / 文案内容事实源。

> `config/config.yaml` 和 `config/secrets.yaml` 都属于本地私有配置，不会提交到 Git。

## 🚀 运行与发布

```bash
python scripts/update_report.py             # 更新报告（默认模板或本地覆盖配置）
python scripts/update_report.py --publish   # 发布模式（需先补本地 publish / secrets 配置）
```

> `--publish` 会先正常更新源码工作区根目录 `index.html`，再按 `publish.github.commit_files` 只把当天这份报告推到正式仓。若 GitHub Pages 直接服务当前源码仓的 `main` 分支，请把 `publish.github.pages_repo_root` 留空；不要再额外指向一个同 remote / 同分支的瘦 Pages 仓。




## ✅ 推荐使用顺序

1. 安装依赖：`pip install -r requirements.txt`
2. 先直接运行一次：`python scripts/update_report.py`
3. 需要自定义时，再复制并修改 `config/config.yaml`
4. 需要发布时，再补 `config/secrets.yaml` 并执行 `--publish`

## 📚 进一步说明

- **[WORKFLOW.md](WORKFLOW.md)** - 详细工作流程、排障步骤、验证方式
- **[DESIGN.md](DESIGN.md)** - 架构设计
- **[SKILL.md](SKILL.md)** - 技能定位与入口导航




## 📝 更新时间

建议在交易日收盘后（15:00 之后）执行更新。

---

**版本**: v2.2.0 | **最后更新**: 2026-04-07
