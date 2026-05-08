# 项目审计规程（本地私有）

**版本**: 1.1  
**最后更新**: 2026-04-22  
**目的**: 定期梳理项目结构、检查敏感信息、验证文档一致性，并守住公开仓边界

---

## 定位

- 本文是 `python scripts/audit_project.py` 的**执行细则**。
- 发布前"必须不要漏什么"由 `RELEASE_RUNBOOK.md` 管；本文负责解释"审计到底查什么"。
- 本文属于**本地治理文档**，不进入公开仓。

## 核心审计模块

项目审计分为 **4 大模块**，按"结构 → 安全 → 文档 → Git 边界"推进。

### 模块 1：结构审计

**目的**：梳理目录结构，识别冗余、重复或孤立文件。

**检查项**：
1. 列出目录及大小
2. 找出空目录
3. 发现重复文件
4. 识别临时/调试文件是否已归位
5. 验证文件夹职责划分是否清晰

### 模块 2：敏感信息审计

**目的**：扫描并清除任何敏感数据泄露风险。

**检查项**：
1. 搜索本地绝对路径、`file:///` 路径
2. 搜索 API 密钥、Token、密码等凭证
3. 搜索私有规则 / 本机协作协议引用（如 `~/.codebuddy/...`）
4. 搜索 webhook、企业内部链接或"internal only / confidential"标记
5. 检查日志和缓存文件中的敏感内容

### 模块 3：文档一致性审计

**目的**：验证文档描述与实际代码 / 目录边界是否一致。

**检查项**：
1. `SKILL.md` / `README.md` / `WORKFLOW.md` 的路径和说明是否仍有效
2. `docs/` 中是否只保留稳定公开补充文档
3. 草案 / 模板 / incident / 私有规程是否已迁出 `docs/`
4. 配置示例是否与实际公开模板一致
5. 文档中的相对路径、内部链接是否可解析
6. 知识文档内容是否与当前代码/数据源一致（REQ-173 产出的 6 篇，按触发场景核对）：
   - 01-数据源与工具生态：是否反映当前实际使用的数据源
   - 02-外部数据合规入门：是否覆盖已知反爬/限频/合规风险
   - 03-A股行业分类体系对比：行业分类是否有新变化
   - 04-ETF估值方法论：估值方法/数据源是否与 ValuationEngine 一致
   - 05-量化估值因子入门：因子定义是否与 quant_factors.py 一致
   - 06-技术分析简介：技术指标是否与代码实现一致

### 模块 4：Git 边界审计

**目的**：优化 `.gitignore`，确保不会意外提交本地治理面或运行面内容。

**检查项**：
1. `.gitignore` 是否覆盖 `PLAN.md`、`plans/`、`statusbar.config.md`、`CONTRIBUTING.md`、`RELEASE_RUNBOOK.md`、`AUDIT_RUNBOOK.md`
2. `data/`、`logs/`、`_working/`、`.backup/`、`outputs/` 是否被忽略
3. `git ls-files` 是否错误跟踪了禁止提交对象
4. 是否有大文件、缓存或一次性产物被意外纳入版本控制
5. `git status` 是否只呈现预期改动

---

## 执行方式

### 完整审计（推荐，发布前 / 每周自动化）

```bash
python scripts/audit_project.py --full --report-only
```

**适用场景**：
- 发布前
- 每周固定巡检
- 大改后做边界回归

### 快速审计

```bash
python scripts/audit_project.py --quick
```

**适用场景**：
- 临时确认结构和敏感信息
- 小改后快速排雷

### 模块级审计

```bash
python scripts/audit_project.py --structure
python scripts/audit_project.py --security
python scripts/audit_project.py --documentation
python scripts/audit_project.py --git-config
```

---

## 审计通过标准

### 结构审计通过标准

- 根目录没有明显的一次性排查残留
- `docs/`、`scripts/`、`config/`、`tests/` 职责清晰
- 空目录只允许是明确保留的临时/输出目录

### 敏感信息审计通过标准

- 无本地绝对路径与 `file:///` 泄露
- 无 token / secret / password / webhook 暴露
- 无私有规则或本机协作协议出现在公开文档面

### 文档一致性通过标准

- 公开文档中所有路径都能在当前仓库内自洽
- `docs/` 只保留稳定公开补充文档
- 草案、复盘、私有规程都不再留在 `docs/`

### Git 边界通过标准

- `git ls-files PLAN.md plans statusbar.config.md CONTRIBUTING.md RELEASE_RUNBOOK.md AUDIT_RUNBOOK.md config/config.yaml config/secrets.yaml` 返回空结果
- `.gitignore` 能覆盖所有本地治理面与运行面对象
- `git status` 中没有意外新增的私有文档或运行产物

---

## 自动化接入（CodeBuddy）

### 周期任务建议

- **名称**：`每周审计 etf-report`
- **频率**：每周一 09:00
- **工作目录**：`c:/Users/julentan/CodeBuddy/StockMarket/.codebuddy/skills/etf-report`
- **执行内容**：运行 `python scripts/audit_project.py --full --report-only`，总结结构、敏感信息、文档一致性和 Git 边界结果

### 自动化输出要求

自动化结果至少应回答：
1. 本周是否发现新的公开仓泄露风险
2. `docs/` 是否混入了不该留在那里的文档
3. `.gitignore` / `git ls-files` 是否仍守住本地治理边界
4. 哪些文件需要人工跟进

---

## 常见修复动作

### 修复 1：`docs/` 被草案污染

- 把文档迁到对应 `plans/REQ-XXX.md`
- 若是复盘，编号为 `plans/BUG-XXX.md`
- 若是私有规程，迁到技能根目录

### 修复 2：禁止提交对象被错误跟踪

- 先更新 `.gitignore`
- 再执行 `git rm --cached` 或 `git rm --cached -r` 清理索引
- 最后回看 `git ls-files` 是否已返回空结果

### 修复 3：公开文档泄露本地信息

- 删除本地绝对路径、`file:///` 地址、私有规则引用
- 回看 `README.md` / `SKILL.md` / `WORKFLOW.md` 是否还有同类口径

---

## 执行口径

- 周期审计是**排雷机制**，不是发布动作本身。
- 发布前如果跳过审计，视为 `RELEASE_RUNBOOK.md` 未完成。
- 若审计发现边界问题，优先修边界，再继续功能或发布动作。
