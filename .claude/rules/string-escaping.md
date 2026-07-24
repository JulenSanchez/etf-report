---
description: 跨上下文字符串拼接禁令、Windows 路径、argparse help 规范
alwaysApply: true
priority: P1
---

# 字符串拼接与转义规则

## Why

REQ-355/REQ-360 开发中反复踩坑：
- `argparse` help 含中文 `%%` 触发 format bug
- Python 生成 HTML 时 inline `onclick` 三层转义失败（`onclick=\"dmFoo(\\\'' + code + '\\\')\"`），最后只能改成事件委托才工作
- `python -c` 在 PowerShell 下引号嵌套屡次失败

跨上下文字符串拼接（Python str → HTML attr → JS string）是高危操作，每层有自己的引号和转义规则，人类和 AI 都容易写错。

## 禁止：跨上下文 inline 字符串拼接

❌ Python 生成 HTML 时用 `+` 拼接 inline 事件：

```python
etfHtml += '<span onclick="dmFoo(\'' + code + '\')">'
```

✅ 用 `data-attribute` + 事件委托：

```python
# Python 侧只生成 data 属性
etfHtml += '<span class="dm-foo" data-code="' + code + '">'
```

```js
// JS 侧统一委托
document.addEventListener('click', e => {
  const t = e.target.closest('.dm-foo');
  if (t) dmFoo(t.dataset.code);
});
```

## 禁止：argparse help 含 `%` 或中文

`argparse` 内部用 `%` 做 format，help 字符串里的 `%` 会被解释。

❌ `help='MDD 槽位宽度 (default: 1.0%%)'`
✅ `help='MDD slot width (default: 1.0)'`（英文 + 无 `%`）

如果必须含中文，用 `%(default)s` 占位符并传 `formatter_class`，或干脆移到 epilog。

## 强制：跨语言拼接用模板或 DOM API

❌ f-string 拼接 inline 事件：
```python
f'<div onclick="foo(\'{code}\')">'
```

✅ 选项 A：`<template>` + `cloneNode` + `addEventListener`
✅ 选项 B：`document.createElement` + `el.dataset.code = code` + `el.addEventListener`
✅ 选项 C：必须 inline 时用 `&quot;` / `&#39;` HTML 实体，不混用引号

## 强制：Python 脚本不用 `-c`，写文件

→ 详见 [no-python-inline.md](no-python-inline.md)，此处不重复。

## 强制：Windows 路径用 raw string 或正斜杠

❌ `"C:\Users\julentan\etf-report\data"`
✅ `r"C:\Users\julentan\etf-report\data"`
✅ `"C:/Users/julentan/etf-report/data"`

JSON 字符串里的 Windows 路径必须用正斜杠或双反斜杠。

## 强制：warnings.filterwarnings 只用于已修根因后的兜底

❌ 先抑制再假装没事：
```python
warnings.filterwarnings('ignore', message='range not divisible by step')
# bounds 不对齐 step，TPE 采样空间有偏差
```

✅ 先修根因，抑制只作为兼容旧 optuna 版本的兜底：
```python
# 1. 根因修复
lo = math.floor(lo / step) * step
hi = math.ceil(hi / step) * step
# 2. 兜底（如有必要）
warnings.filterwarnings('ignore', message='...')
```

## 自检清单

写代码前问自己：
- [ ] 这段字符串会跨几个上下文（Python/HTML/JS/JSON/Shell）？
- [ ] 每个 `+` 拼接点都检查过引号和转义了吗？
- [ ] 能否用 `data-attribute` + 事件委托替代 inline 事件？
- [ ] `help=` 字符串里有 `%` 吗？
- [ ] 路径里有反斜杠吗？
