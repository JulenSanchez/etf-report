# ETF Report — 开发者指南

> **读到本文件 = 你是开发者。** 如果你是 clone 仓库来使用技能的用户，请回到 `README.md`。

## AI 身份识别

当你（AI Agent）在技能目录下检测到本文件存在时：

- **你的角色是开发者**，不是普通使用者
- 你有权感知需求看板、Bug 状态、状态网络配置、审计规则等内部状态
- 你应优先读本文件，再按下方首读顺序展开

## 开发者首读顺序

| 顺序 | 文件 | 读什么 |
|------|------|--------|
| 1 | `CONTRIBUTING.md`（本文件） | 身份识别 + 目录全景 + 事实源分层 + 开发约定 |
| 2 | `PLAN.md` | 需求管理规则、编号守卫、版本发布入口 |
| 3 | `plans/Board.md` | 当前版本、in_progress、活跃 Bug、ID 计数器 |
| 4 | 相关 `plans/REQ-*.md` / `plans/BUG-*.md` | 边界决策、用户覆盖、落地记录 |
| 5 | `statusbar.config.md` | 状态网络配置（States / Actions / Routing / Display） |
| 6 | `QUANT_SYSTEM.md` | 量化回测 / Tuner / preset / payload 的系统入口与变更路由 |
| 7 | `runbooks/QUANT_RUNBOOK.md` | 量化系统启动、数据刷新、payload 运维与排障 |
| 8 | `SKILL.md` / `README.md` | 对外公开面描述，不要让它们反向覆盖开发事实 |
| 9 | `config/*.yaml` / `scripts/*.py` / `tests/` | 实现事实源 |

## 完整目录全景图

技能目录分两区：**Git 跟踪**（随仓库提交）和**运行产物**（`.gitignore` 排除，本地生成）。

### 🏠 Git 跟踪（随仓库提交）

```
etf-report/
├── index.html                  ← 报告页面主体
├── assets/
│   ├── css/report.css          ← 报告样式
│   │   └── debug.css           ← 调试样式
│   └── js/
│       ├── report-main.js      ← 报告主逻辑
│       ├── chart-lifecycle.js  ← 图表生命周期
│       └── debug-toolbar.js    ← 调试工具栏
├── config/
│   ├── config.example.yaml     ← 公开配置模板（clone 后默认生效）
│   ├── secrets.example.yaml    ← 敏感配置模板
│   ├── holdings.yaml           ← 成分股事实源
│   ├── editorial_content.yaml  ← 解释层文案
│   ├── editorial_sources.yaml  ← 编辑源配置
│   └── compliance_rules.yaml   ← 合规规则
├── scripts/                    ← Python 主流程与辅助脚本
├── tests/                      ← 回归测试
├── docs/                       ← 参考文档
├── .github/workflows/test.yml  ← CI 配置
├── CONTRIBUTING.md             ← 开发者指南（本文件）
├── QUANT_SYSTEM.md             ← 量化回测系统入口
├── PLAN.md                     ← 需求管理入口
├── plans/                      ← 需求看板（Board/Backlog/Archive/REQ-*）
├── statusbar.config.md         ← 状态网络配置
├── runbooks/                   ← 运行规程（QUANT/RELEASE/AUDIT）
├── SKILL.md                    ← AI 技能描述卡（对外）
├── README.md                   ← 仓库入口（对外）
├── WORKFLOW.md                 ← 执行手册（对外）
├── DESIGN.md                   ← 架构设计（对外）
├── requirements.txt            ← Python 依赖
└── .gitignore
```

### 📦 运行产物（.gitignore 排除）

```
├── data/
│   ├── etf_full_kline_data.json    ← K 线数据
│   ├── etf_realtime_data.json      ← 实时行情
│   ├── corporate_action_events.json ← 份额变动事件
│   ├── quant/                      ← 量化回测 CSV
│   └── runtime_payload.js          ← 前端运行时载荷
├── logs/                           ← 每日结构化运行日志
├── outputs/                        ← 兼容/手工导出临时区
├── research/                       ← 参数搜索等研究产出
├── _working/                       ← 一次性排查输出区
├── .backup/                        ← 事务回滚快照
├── config/config.yaml              ← 本地覆盖配置
├── config/secrets.yaml             ← 敏感配置（API 密钥等）
├── config/quant_user_overrides.yaml ← Tuner 用户覆盖参数
└── __pycache__/                    ← Python 缓存
```

## 三层事实源

当多份文档看起来冲突时，按此优先级处理：

### 1. 开发治理事实源（最高优先级）

| 文件 | 职责 |
|------|------|
| `PLAN.md` | 需求管理规则、编号守卫、版本发布入口 |
| `plans/Board.md` | 当前版本、下一个 ID、活跃状态 |
| `plans/REQ-*.md` / `BUG-*.md` | 需求/缺陷的边界决策与落地记录 |
| `statusbar.config.md` | 状态网络配置 |
| 工作区规则（`.codebuddy/rules/`） | 需求守卫、状态栏协议宿主 |

### 2. 对外公开事实源

| 文件 | 职责 |
|------|------|
| `README.md` | 外部用户配置与运行入口 |
| `SKILL.md` | AI 技能描述卡 |
| `WORKFLOW.md` | 执行手册 |
| `DESIGN.md` | 架构设计 |
| `docs/` | 参考文档 |

### 3. 实现事实源

| 文件 | 职责 |
|------|------|
| `scripts/*.py` | 系统实际上怎么工作 |
| `config/*.yaml` | 哪些配置项真的生效 |
| `tests/*.py` | 回归验证 |

**一句话**：开发治理描述"现在项目是什么状态"，公开文档描述"怎么用"，代码描述"实际上怎么实现"。

## 开发固定原则

1. **编号守卫**：只要事项会进入持续推进、状态流转、归档复盘，就先按 `PLAN.md` 规则申请 `REQ` / `BUG` 编号
2. **边界原则**：不要把开发治理文件的引用写回 `SKILL.md` / `README.md`；不要把本地敏感配置写回公开模板
3. **用户覆盖记录**：如果用户推翻 AI 建议，把原因写进最近的 `REQ-XXX.md` 或 `Board.md`
4. **临时产物**：根目录不新增一次性 `*.txt` / `*.bak*`；临时排查输出放 `_working/`；长期复用样本放 `tests/fixtures/`

## 常见开发任务入口

| 任务 | 入口 |
|------|------|
| 推进需求 / 修 Bug | `PLAN.md` → `plans/Board.md` → 补编号 → 改文件 |
| 发布版本 | `runbooks/RELEASE_RUNBOOK.md`（唯一门禁） |
| 改公开导航 | 先改 `README.md` / `SKILL.md`，再检查本文件边界是否需同步 |
| 改配置模板 | 读 `config/config.example.yaml`，确认是否影响 `README.md` |
| 接发布链路 | 读 `scripts/notifier.py` / `scripts/deployer.py` |
| 量化回测 / Tuner / preset / payload | `QUANT_SYSTEM.md` → 按变更路由进入 `BACKTEST_ENGINE.md` / `QUANT_RUNBOOK.md` / `quant_contract.py` |
| 量化调试 / 调参 | `runbooks/QUANT_RUNBOOK.md` → 启动 Tuner → 交互调参 → Save to YAML |
