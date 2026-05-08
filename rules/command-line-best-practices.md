---
description: 
alwaysApply: true
enabled: true
updatedAt: 2026-03-17T06:44:22.978Z
provider: 
---

# 命令行操作最佳实践

## 1. 禁止使用 `python -c` 注入代码

**永远不要**使用 `python -c "..."` 或 `python -c '...'` 的方式执行代码。

原因：
- Windows PowerShell 的引号嵌套极易出错
- 跨平台行为不一致
- 调试困难

## 2. 临时 Python 脚本管理

**临时脚本目录**：`C:\Users\julentan\temp_scripts\`

**命名规则**：`temp_script_YYYYMMDD_HHMMSS.py`（带时间戳，避免冲突）

**使用方式**：
```
1. 写入脚本：write_to_file("C:/Users/julentan/temp_scripts/temp_script_20250317_143022.py", "代码内容")
2. 执行脚本：python C:/Users/julentan/temp_scripts/temp_script_20250317_143022.py
```

**自动清理**：每周定时清理一周以前的临时脚本（由自动化任务执行）

## 3. 简单任务优先使用原生 Shell 命令

| 任务 | ❌ 错误做法 | ✅ 正确做法 |
|------|------------|------------|
| 列出目录 | `python -c "import os; print(os.listdir(...))"` | `dir path` 或 `Get-ChildItem path` |
| 读取文件 | `python -c "print(open(...).read())"` | `type file` 或 `cat file` |
| 检查文件存在 | `python -c "import os; print(os.path.exists(...))"` | `Test-Path path` |
| 创建目录 | `python -c "os.makedirs(...)"` | `mkdir path` |
| 删除文件 | `python -c "os.remove(...)"` | `del file` 或 `Remove-Item file` |

## 4. 决策流程

遇到需要执行代码的场景时：

```
是否是简单的文件/目录操作？
  ├─ 是 → 使用 shell 原生命令 (dir, type, mkdir, del 等)
  └─ 否 → 是否需要复杂逻辑？
            ├─ 是 → 写入带时间戳的临时脚本后执行
            └─ 否 → 考虑是否有更直接的工具可用
```

## 5. Windows 终端环境注意事项

### 5.1 使用绝对路径，避免 cd 切换

**错误：**
```powershell
cd /d "e:\project" && python script.py  # /d 是 CMD 语法，PowerShell 不识别
cd e:\project
python script.py  # 每次 execute_command 是独立 session，cd 无效
```

**正确：**
```powershell
python e:\project\script.py  # 直接使用绝对路径
```

### 5.2 创建目录优先用 write_to_file

**错误：**
```powershell
mkdir "e:\project\_working"  # 可能因路径存在报错
New-Item -ItemType Directory ...  # CMD/PowerShell 语法混淆
```

**正确：**
```
使用 write_to_file 创建占位文件（如 .gitkeep），目录会自动创建
```

### 5.3 避免参数包含空格

**错误：**
```powershell
python script.py --title "Luna Frontend"  # 空格可能导致解析问题
```

**正确：**
```powershell
python script.py --title "Luna_Frontend"  # 下划线代替空格
python script.py --title Luna-Frontend    # 或使用连字符
```

### 5.4 脚本输出使用 ASCII 字符

**错误：**
```python
print("⭐" * 3)  # Windows 终端 GBK 编码不支持 emoji
```

**正确：**
```python
print("*" * 3)  # 使用 ASCII 字符
# 或设置 UTF-8 编码：
# import sys; sys.stdout.reconfigure(encoding='utf-8')
```

### 5.5 CMD 与 PowerShell 语法区别

| 操作 | CMD | PowerShell |
|------|-----|------------|
| 切换盘符 | `cd /d e:\path` | `cd e:\path` 或 `Set-Location` |
| 链接命令 | `cmd1 && cmd2` | `cmd1; cmd2` 或 `cmd1 -and cmd2` |
| 环境变量 | `set VAR=value` | `$env:VAR = "value"` |
| 删除文件 | `del file` | `Remove-Item file` |

**建议**：优先使用跨平台兼容的方式，或明确使用 PowerShell 语法。

## 6. execute_command 工具特性

- **每次调用是独立 session**：工作目录不会保留
- **默认使用 PowerShell**：避免 CMD 特有语法
- **输出可能被截断**：长输出考虑重定向到文件