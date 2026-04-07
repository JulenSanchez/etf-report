# ETF Report 安全发布工作流

## 核心原则

1. **本地验证优先** - 所有改动必须在本地通过检查才能推送
2. **分支保护** - 主分支（main/master）受保护，需要 PR 审查
3. **自动化检查** - 提交前自动运行质量检查
4. **明确的推送审批** - 每次向 GitHub 推送都需要明确确认

## 工作流步骤

### Phase 1: 本地开发与验证

```bash
# 1. 确认当前分支
git branch -v

# 2. 创建特性分支（用于修改）
git checkout -b feature/update-kline-data
# 或
git checkout -b fix/deploy-folder-cleanup

# 3. 进行修改...
# 编辑文件、测试等

# 4. 本地验证清单
- [ ] 运行 update_report.py 验证功能正常
- [ ] 检查生成的 index.html 数据完整
- [ ] 验证日志系统正常工作
- [ ] 确认没有调试代码/敏感信息

# 5. 查看修改概览
git diff
git diff --stat
```

### Phase 2: 暂存与本地提交

```bash
# 1. 分阶段暂存（不要一次性 git add .）
git add scripts/update_report.py
git add WORKFLOW.md
git status  # 验证暂存内容

# 2. 检查暂存的修改
git diff --cached

# 3. 本地提交（带描述）
git commit -m "fix: Update HTML file path in update_report.py

- Fixed path reference from OUTPUTS_DIR to HTML_FILE
- Ensures K-line data syncs to root index.html
- Verified with test run on 2026-04-07"

# 4. 查看本地提交历史
git log -3 --oneline
```

### Phase 3: 预推送检查

```bash
# 1. 检查与远程的差异
git fetch origin
git log origin/master..HEAD --oneline  # 显示本地有哪些新提交

# 2. 预览将要推送的改动
git diff origin/master HEAD > proposed_changes.diff

# 3. 预推送检查清单
- [ ] 提交消息清晰明确
- [ ] 没有包含调试分支或临时提交
- [ ] 没有包含敏感信息（密钥、密码等）
- [ ] 所有依赖已更新（requirements.txt 等）
- [ ] 文档已同步更新
- [ ] .gitignore 配置正确（不上传 data/、logs/ 等）
```

### Phase 4: 安全推送

```bash
# 1. 推送到远程特性分支（安全！不直接修改主分支）
git push origin feature/update-kline-data
# 这会在 GitHub 上创建新分支，不影响 master

# 2. 在 GitHub 上创建 Pull Request
# 访问 https://github.com/JulenSanchez/etf-report/pull/new/feature/update-kline-data
# 手动审查后合并到 master

# 3. 如果需要直接推送到 master（仅限合并后清理）
git checkout master
git pull origin master  # 同步最新主分支
git push origin master  # 推送

# 4. 推送后清理
git branch -d feature/update-kline-data  # 删除本地分支
git push origin --delete feature/update-kline-data  # 删除远程分支
```

## 自动化检查脚本

### pre-commit Hook（提交前自动检查）

在 `.git/hooks/pre-commit` 中添加：

```bash
#!/bin/bash

echo "[Pre-commit Check] Running safety checks..."

# 1. 检查敏感信息
if grep -r "password\|secret\|api_key\|token" . --exclude-dir=.git 2>/dev/null; then
    echo "ERROR: Found potential secrets in code!"
    exit 1
fi

# 2. 检查大文件（> 50MB）
for file in $(git diff --cached --name-only); do
    size=$(ls -lh "$file" 2>/dev/null | awk '{print $5}')
    if [[ $size == *"M" ]] && (( $(echo "${size%M} > 50" | bc -l) )); then
        echo "ERROR: File $file is too large ($size)"
        exit 1
    fi
done

# 3. 检查 Python 语法
git diff --cached --name-only | grep '\.py$' | while read file; do
    python -m py_compile "$file" 2>/dev/null || {
        echo "ERROR: Python syntax error in $file"
        exit 1
    }
done

echo "[Pre-commit Check] All checks passed!"
exit 0
```

### pre-push Hook（推送前自动检查）

在 `.git/hooks/pre-push` 中添加：

```bash
#!/bin/bash

echo "[Pre-push Check] Running final safety checks..."

protected_branches="master|main"
current_branch=$(git rev-parse --abbrev-ref HEAD)

# 1. 不允许直接推送到 master（必须通过 PR）
if [[ $current_branch =~ $protected_branches ]]; then
    echo "WARNING: You are about to push to '$current_branch'"
    echo "Recommended workflow:"
    echo "  1. Push to feature branch: git push origin feature/..."
    echo "  2. Create PR on GitHub"
    echo "  3. Merge after review"
    read -p "Continue? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Push aborted."
        exit 1
    fi
fi

# 2. 检查提交数量
commit_count=$(git rev-list --count origin/master..HEAD)
if [ $commit_count -gt 5 ]; then
    echo "WARNING: You are pushing $commit_count commits"
    read -p "Continue? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "[Pre-push Check] Proceeding with push..."
exit 0
```

## 推荐工作流（安全版本）

### 日常开发修改

```bash
# 1. 创建特性分支
git checkout -b feature/description

# 2. 进行修改和本地测试
python scripts/update_report.py

# 3. 分段暂存（避免误上传）
git add scripts/
git add docs/

# 4. 提交
git commit -m "desc: message"

# 5. 推送到远程特性分支
git push origin feature/description

# 6. 在 GitHub 创建 PR，让用户手动审查

# 7. 合并到 master 后清理
git checkout master
git pull origin master
git branch -d feature/description
```

### 直接修复（快速路径，谨慎使用）

仅在确认改动安全的情况下使用：

```bash
# 1. 本地验证（必须！）
python scripts/update_report.py
# 检查输出...

# 2. 直接推送
git add .
git commit -m "fix: description"
git push origin master

# 3. 推送后监控
git log -1  # 验证提交
git status  # 确认本地干净
```

## 安全检查清单

| 检查项 | 必须 | 说明 |
|------|------|------|
| 本地功能测试 | ✅ | 运行 update_report.py 验证 |
| 代码审查 | ✅ | 检查 git diff 内容 |
| 敏感信息检查 | ✅ | 确保没有密钥/密码 |
| 提交消息质量 | ✅ | 清晰描述改动 |
| 分支策略 | ✅ | 不直接推送 master（首选） |
| 文件大小检查 | ✅ | 避免上传大文件 |
| 依赖同步 | ✅ | requirements.txt 最新 |

## 紧急回滚

如果推送后发现问题：

```bash
# 1. 立即检查
git log -3 --oneline
git show HEAD

# 2. 本地重置（不影响远程）
git reset --hard HEAD~1

# 3. 强制推送回滚（谨慎！仅在必要时）
git push origin master --force
# 注意：这会改写历史，通知团队成员

# 4. 验证
git log -1
```

## 配置建议

### GitHub 仓库设置

1. **分支保护**（Settings → Branches → Protect main）
   - ✅ 要求 PR review
   - ✅ 要求测试通过
   - ✅ 禁止强制推送

2. **Webhook 配置**
   - 推送后自动运行测试
   - 失败时发送通知

3. **成员权限**
   - 限制 admin 权限
   - 代码 review 需要指定人员

## 快速参考

```bash
# 查看当前状态
git status

# 查看修改
git diff

# 安全推送工作流
git checkout -b feature/name
git add .
git commit -m "message"
git push origin feature/name
# → 在 GitHub 创建 PR → 审查 → 合并

# 查看推送历史
git log --oneline -10

# 同步远程更新
git fetch origin
git pull origin master
```
