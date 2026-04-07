# Git 基础知识 - Master vs Main 分支

## 快速问答

### Q: master 分支是什么？
**A:** `master` 是 Git 的默认分支名称（传统名字）。它代表你项目的"主干"版本。

### Q: main 分支是什么？
**A:** `main` 是 GitHub 在 2020 年推荐使用的新默认分支名称（取代 `master`）。功能完全一样，只是名字不同。

### Q: 为什么有两个分支？
**A:** 没有两个分支！现在你的仓库只有一个主分支，但这个主分支叫 `master` 还是 `main`，取决于：
- **本地**：`git init` 时使用的默认名称
- **GitHub**：仓库设置中配置的默认分支

## 你现在的状态

```
本地仓库：master 分支 ✅
  ↓ (git push)
GitHub 仓库：也是同一个分支
  （名字可能显示为 main 或 master）
```

## 统一分支名称（改为 main - GitHub 标准）

如果你想保持与 GitHub 标准一致，改成 `main`：

```bash
# 1. 本地重命名分支
git branch -m master main

# 2. 推送到 GitHub 并设置为默认
git push -u origin main --force

# 3. 删除远程的 master 分支
git push origin --delete master

# 4. 验证
git branch -a
# 应该看到：origin/main
```

## 分支概念（比喻）

想象你的项目就像一个故事版本历史：

```
v1.0 → v1.1 → v1.2 → v2.0 (master/main 分支)
              ↓
            v1.1-fix (修复分支)
```

### 为什么需要分支？

假设你正在开发新功能，但突然发现前一个版本有 bug。你可以：

1. **主分支（master/main）** - 存放稳定版本
   - 用户看到的版本
   - 直接发布的版本
   
2. **特性分支（feature/xxx）** - 开发新功能
   - 不影响主分支
   - 开发完成后合并到主分支

3. **修复分支（fix/xxx）** - 修复 bug
   - 从主分支创建
   - 修复完成后合并回主分支

### 实际工作流示意

```
master/main ─────────────●────────────●────────→ 主干版本（用户使用）
              ↓                        ↑
         (feature/new-ui)        （开发完成，合并）
              ├─────────────────────→ ●
              └─ 开发新 UI 功能

master/main ───────────●──────●────────────────→ 主干版本
                       ↑      ↑
                   发现bug  (hotfix/bug-123)
                       │      │
                       └──●───┘
                      修复完成，合并回主干
```

## 你当前的简单情况

因为你只有一个仓库，只需要推送到一个主分支即可。你有两种选择：

### 选择 1: 保持使用 master（当前状态）
```bash
git push origin master
# 完成！内容在 GitHub 的 master 分支上
```

### 选择 2: 改成使用 main（推荐）
```bash
# 1. 改名
git branch -m master main

# 2. 推送
git push -u origin main --force

# 3. 删除旧 master
git push origin --delete master

# 完成！内容在 GitHub 的 main 分支上
```

## GitHub 页面设置

为了让 GitHub Pages 正确识别你的 `index.html`，需要在仓库设置中配置：

1. **访问仓库设置**
   - 打开 https://github.com/JulenSanchez/etf-report/settings

2. **找到 "Pages" 设置**
   - 左边菜单 → Pages
   - Source 选择 "Deploy from a branch"
   - Branch 选择 "main"（或 "master"）
   - 保存

3. **验证部署**
   - 稍后会在 https://julensan.github.io/etf-report/ 看到你的 index.html
   - 或者根据仓库设置页面显示的 URL

## 完整步骤（推荐）

如果你要现在改成 `main` 分支：

```bash
# 1. 进入项目目录
cd "C:\Users\julentan\CodeBuddy\Claw\.codebuddy\skills\etf-report"

# 2. 本地重命名 master → main
git branch -m master main

# 3. 推送到 GitHub（--force 会覆盖）
git push -u origin main --force

# 4. 删除远程 master 分支
git push origin --delete master

# 5. 验证
git branch -a
git log -1
```

推送后，GitHub 会自动识别 `main` 分支并设置为默认分支。

## 简单总结

| 概念 | 说明 |
|------|------|
| **master** | Git 的传统默认分支名 |
| **main** | GitHub 现在推荐的默认分支名 |
| **分支** | 独立的开发线，不影响主分支 |
| **你的情况** | 目前只有一个主分支，叫 master（可以改成 main） |
| **下一步** | 推送到 GitHub，配置 Pages 设置，完成 |

## 常用 Git 命令速查

```bash
# 查看分支
git branch           # 本地分支
git branch -a        # 本地 + 远程分支

# 创建/切换分支
git checkout -b feature/name    # 创建并切换
git checkout main               # 切换到 main

# 推送
git push origin main            # 推送 main 分支

# 重命名
git branch -m old-name new-name # 重命名分支

# 删除分支
git branch -d feature/name           # 删除本地
git push origin --delete feature/name # 删除远程
```

这样应该能帮你理解了！如果还有疑问，继续问我。
