# etf-report 项目规则索引

## P0 铁律（违反即事故）

| 文件 | 用途 |
|------|------|
| [git-branches.md](.claude/rules/git-branches.md) | 分支策略、提交门禁（commit/push 必须用户触发）、回退方式 |
| [no-python-inline.md](.claude/rules/no-python-inline.md) | 禁止 `python -c`，一律写临时脚本 |

## P1 强约束（每次编码前必读）

| 文件 | 用途 |
|------|------|
| [expose-bugs.md](.claude/rules/expose-bugs.md) | 暴露 bug 而非隐藏——反模式/正模式对照 + 自检清单 |
| [string-escaping.md](.claude/rules/string-escaping.md) | 跨上下文字符串拼接禁令、Windows 路径、argparse help 规范 |

## P2 场景参考（遇特定场景时查阅）

| 文件 | 用途 |
|------|------|
| [tuner-hot-reload.md](.claude/rules/tuner-hot-reload.md) | Tuner 前端热加载规则：改 HTML 不需重启，改 .py 才需 |

## 规则冲突解决

当多个规则同时适用时，优先级：**P0 > P1 > P2**。同级冲突时，更具体的规则优先（如 expose-bugs 的"最小修复"和 git-branches 的"逐条回退"互补——前者管代码修改范围，后者管 git 操作回退方式）。
