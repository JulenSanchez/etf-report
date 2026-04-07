# 项目审计工作流 (AUDIT_WORKFLOW)

**版本**: 1.0  
**最后更新**: 2026-04-07  
**目的**: 定期梳理项目结构、检查敏感信息、验证文档一致性、评估 Git 配置

---

## 📋 快速导航

- [核心审计流程](#核心审计流程)
- [执行方式](#执行方式)
- [检查清单](#检查清单)
- [审计报告](#审计报告)
- [常见修复](#常见修复)

---

## 🎯 核心审计流程

项目审计分为 **4 大模块 × N 个检查项**，采用从外到内、从宏观到微观的分析策略。

### 模块 1: 结构审计 (Structure Audit)

**目的**: 梳理目录结构，识别冗余、重复或孤立的文件

**检查项**:
1. 列出所有目录及大小
2. 找出空目录（无实际内容的文件夹）
3. 发现重复文件（同名或相似内容）
4. 识别临时/调试文件
5. 验证文件夹职责划分

**关键发现示例**:
```
❌ 冗余: references/ 目录已迁移，应删除
⚠️  警告: outputs/index.html 是备用版，主版在根目录
✅ 正常: scripts/ 中的所有文件都有对应文档说明
```

---

### 模块 2: 敏感信息审计 (Security Audit)

**目的**: 扫描并清除任何敏感数据泄露风险

**检查项**:
1. 搜索个人身份信息（邮箱、电话、QQ、微信）
2. 搜索 API 密钥、Token、密码
3. 搜索公司/项目名称和内部链接
4. 搜索文档中的 "internal only" / "confidential" 标记
5. 检查日志和缓存文件中的敏感内容

**扫描模式**:
```
# 个人信息
julensanchez, julentan, @qq.com, @163.com, 手机号

# 身份验证
api_key, auth_token, password, secret, private_key, Bearer

# 企业信息
webhook, 钉钉, 企业微信, 公司名, 项目代号

# 文档标记
@everyone, @all, internal.only, confidential, do.not.share
```

**关键发现示例**:
```
✅ 安全: 未找到任何 Token、密码、私钥
✅ 安全: 日志和缓存中无敏感信息
❌ 泄露: 发现 webhook URL，已从 README.md 中删除
```

---

### 模块 3: 文档一致性审计 (Documentation Audit)

**目的**: 验证文档描述与实际代码实现是否一致

**检查项**:
1. 检查 SKILL.md 中的目录结构是否与实际相符
2. 验证 WORKFLOW.md 中的执行步骤是否有效
3. 检查文档中的路径引用是否正确
4. 确认配置示例与实际配置文件的参数一致
5. 验证文档链接（内部链接、文件引用）

**对比清单**:
```
文档说明                          实际代码                           状态
├── "outputs/ 用于生成报告"  → scripts/update_report.py 第 49 行 ✅
├── "运行时间 ~11 秒"         → 实测 10.8-11.2 秒                 ✅
├── "6 支 ETF 自动分析"       → config.yaml 中配置了 6 支        ✅
└── "生成 index.html"          → 写入根目录（第 142 行）           ✅
```

**关键发现示例**:
```
❌ 不一致: docs/ 中说 "输出到 outputs/"，但实际主输出在根目录
✅ 一致: 所有参数说明与 config.yaml 相符
⚠️  过时: DESIGN.md 中的架构图需要更新
```

---

### 模块 4: Git 配置审计 (Git Config Audit)

**目的**: 优化 .gitignore，确保不会意外提交不该提交的文件

**检查项**:
1. 检查 .gitignore 是否覆盖所有临时文件
2. 验证 _working/ 、logs/、data/ 等目录是否被正确忽略
3. 检查是否有大文件被意外跟踪
4. 验证缓存和输出目录的忽略规则
5. 测试 git status 输出是否干净

**忽略规则检查**:
```
✅ 已忽略: _working/, logs/, data/, .backup/
✅ 已忽略: *.pyc, __pycache__/, .DS_Store
⚠️  警告: outputs/ 中的 HTML 可以忽略（非发布版）
❌ 遗漏: config/secrets.yaml 应被忽略
```

**关键发现示例**:
```
✅ 干净: git status 显示 "nothing to commit"
❌ 问题: 误提交了 logs/debug_*.log（3.5MB）
```

---

## 📊 执行方式

### 完整审计（推荐）

```bash
cd .codebuddy/skills/etf-report
python scripts/audit_project.py --full
```

**预期输出**:
- 控制台：彩色表格汇总结果
- 文件：`logs/audit_<timestamp>.json` 详细报告

---

### 快速审计（10 秒）

```bash
python scripts/audit_project.py --quick
```

**检查项**: 结构 + 敏感信息（跳过文档和 Git 详细检查）

---

### 模块级审计

```bash
# 只检查结构
python scripts/audit_project.py --structure

# 只检查敏感信息
python scripts/audit_project.py --security

# 只检查文档
python scripts/audit_project.py --documentation

# 只检查 Git 配置
python scripts/audit_project.py --git-config
```

---

### 自动化定期审计

在 .codebuddy/automations 中配置：

```bash
# 每周一早上 9 点执行完整审计
# rrule: FREQ=WEEKLY;BYDAY=MO;BYHOUR=9;BYMINUTE=0
python scripts/audit_project.py --full --report-only
```

---

## ✅ 检查清单

### 结构审计检查表

| # | 检查项 | 预期结果 | 状态 |
|---|--------|--------|------|
| 1 | 目录大小合理 | scripts/ < 500KB, docs/ < 200KB | - |
| 2 | 无空目录 | 所有目录都有文件 | - |
| 3 | 无明显重复 | 同名文件不超过 2 个 | - |
| 4 | 临时文件已隔离 | _working/ 和 outputs/ 是唯一临时区 | - |
| 5 | 职责划分清晰 | 每个目录有明确的用途说明 | - |

### 敏感信息检查表

| # | 扫描类型 | 预期结果 | 状态 |
|---|---------|--------|------|
| 1 | 个人身份信息 | 0 项发现 | - |
| 2 | 身份验证凭证 | 0 项发现 | - |
| 3 | 企业信息 | 0 项发现（除非是文档目的） | - |
| 4 | 内部标记 | 0 项发现 | - |
| 5 | 日志敏感内容 | 0 项发现 | - |

### 文档一致性检查表

| # | 检查项 | 方法 | 状态 |
|---|--------|------|------|
| 1 | 目录结构描述准确 | 比对 SKILL.md 与实际目录 | - |
| 2 | 执行步骤有效 | 运行 WORKFLOW.md 中的示例命令 | - |
| 3 | 路径引用正确 | 验证所有相对路径可解析 | - |
| 4 | 配置参数一致 | 对比文档示例与 config.yaml | - |
| 5 | 链接有效 | 检查所有 Markdown 链接 | - |

### Git 配置检查表

| # | 检查项 | 预期结果 | 状态 |
|---|--------|--------|------|
| 1 | .gitignore 覆盖完整 | 包含所有临时目录 | - |
| 2 | 大文件未跟踪 | 所有文件 < 5MB | - |
| 3 | git status 干净 | "nothing to commit, working tree clean" | - |
| 4 | 缓存目录被忽略 | __pycache__, *.pyc, .DS_Store | - |
| 5 | 输出目录被忽略 | outputs/, logs/（可选） | - |

---

## 📋 审计报告格式

### 快速摘要（终端输出）

```
╔═══════════════════════════════════════════════════════╗
║         ETF Report Project Audit Report               ║
║         2026-04-07 20:37:15                           ║
╚═══════════════════════════════════════════════════════╝

[1] Structure Audit
    ├── ✅ All directories have clear purposes
    ├── ✅ No empty directories found
    ├── ⚠️  references/ should be deleted
    ├── ✅ Temporary files properly isolated
    └── Status: 4/5 PASSED

[2] Security Audit
    ├── ✅ No personal information found
    ├── ✅ No credentials leaked
    ├── ✅ No internal information exposed
    ├── ✅ No sensitive logs detected
    └── Status: 4/4 PASSED

[3] Documentation Audit
    ├── ✅ SKILL.md structure matches reality
    ├── ⚠️  WORKFLOW.md needs minor updates
    ├── ✅ All paths are correct
    ├── ✅ Config examples match actual files
    ├── ✅ Internal links are valid
    └── Status: 4/5 PASSED

[4] Git Config Audit
    ├── ✅ .gitignore covers all temporary files
    ├── ✅ No large files tracked
    ├── ✅ Working tree is clean
    ├── ⚠️  outputs/ not yet in .gitignore
    ├── ✅ Cache directories properly ignored
    └── Status: 4/5 PASSED

═══════════════════════════════════════════════════════
TOTAL: 16/19 PASSED ✅
OVERALL STATUS: GOOD (需要 1-2 项修复)
═══════════════════════════════════════════════════════

Recommendations:
1. DELETE: references/ (empty, migration completed)
2. ADD: outputs/ to .gitignore
3. UPDATE: Minor corrections to docs (non-critical)
```

### 详细 JSON 报告

```json
{
  "audit_id": "audit_20260407_203715",
  "timestamp": "2026-04-07T20:37:15",
  "summary": {
    "total_checks": 19,
    "passed": 16,
    "warnings": 2,
    "failures": 1,
    "status": "GOOD"
  },
  "modules": {
    "structure": {
      "passed": 4,
      "total": 5,
      "issues": [
        {
          "severity": "error",
          "item": "references/",
          "description": "Empty directory should be deleted",
          "action": "DELETE"
        }
      ]
    },
    "security": {
      "passed": 4,
      "total": 4,
      "issues": []
    },
    "documentation": {
      "passed": 4,
      "total": 5,
      "issues": [
        {
          "severity": "warning",
          "file": "WORKFLOW.md",
          "description": "Step 5 description doesn't match current implementation",
          "action": "UPDATE"
        }
      ]
    },
    "git_config": {
      "passed": 4,
      "total": 5,
      "issues": [
        {
          "severity": "warning",
          "file": ".gitignore",
          "description": "outputs/ directory not in ignore list",
          "action": "ADD_RULE"
        }
      ]
    }
  },
  "recommendations": [
    {
      "priority": "HIGH",
      "type": "DELETE",
      "target": "references/",
      "reason": "Empty directory (migration completed in previous commits)"
    },
    {
      "priority": "MEDIUM",
      "type": "ADD_GITIGNORE",
      "rule": "outputs/",
      "reason": "Prevent dev/debug builds from being committed"
    }
  ]
}
```

---

## 🔧 常见修复

### 修复 1: 删除冗余目录

```bash
# 验证目录为空
ls -la references/

# 安全删除
rm -rf references/

# 提交删除
git add .
git commit -m "refactor: remove empty references/ directory"
```

---

### 修复 2: 更新 .gitignore

```bash
# 编辑 .gitignore，添加新规则
echo "outputs/" >> .gitignore

# 从 git 中移除已追踪的文件
git rm --cached outputs/ -r

# 提交
git add .gitignore
git commit -m "ci: add outputs/ to gitignore"
```

---

### 修复 3: 更新文档

```bash
# 编辑 WORKFLOW.md 或相关文档
# 1. 与当前代码对齐
# 2. 更新示例和参数
# 3. 修正路径引用

git add docs/
git commit -m "docs: align documentation with current implementation"
```

---

### 修复 4: 清理敏感信息

如果发现敏感信息泄露：

```bash
# 从 git 历史中移除敏感文件
git filter-repo --invert-paths --path <sensitive-file>

# 或强制重写历史（危险，谨慎使用）
git reset --soft HEAD~<N>
git commit --amend

# 提交
git push --force-with-lease
```

---

## 🔄 定期审计计划

### 建议审计频率

| 审计类型 | 频率 | 触发条件 |
|---------|------|--------|
| **快速审计** | 每周 1 次 | 固定时间（如周一早上） |
| **完整审计** | 每月 1 次 | 月末或发布前 |
| **临时审计** | 按需 | 代码重构、架构变更、数据泄露怀疑 |

### 自动化设置

```bash
# 在项目的 CI/CD 中添加审计步骤
# .github/workflows/audit.yml

name: Weekly Audit
on:
  schedule:
    - cron: '0 9 * * 1'  # 每周一 9:00

jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run Audit
        run: python scripts/audit_project.py --full --report-only
      - name: Upload Report
        uses: actions/upload-artifact@v2
        with:
          name: audit-report
          path: logs/audit_*.json
```

---

## 📞 获取帮助

| 问题 | 解决方案 |
|------|--------|
| 审计失败 | 查看 `logs/audit_<timestamp>.json` 的详细错误 |
| 修复未生效 | 重新运行审计以验证 |
| 找不到敏感信息的位置 | 查看审计报告中的 "matched_lines" 字段 |

---

**版本历史**:
- v1.0 (2026-04-07) - 初版发布
