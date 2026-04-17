# ETF 系统健康检查 - 已知问题和解决方案

## 概述

本文档记录 `REQ-106` 健康检查在当前版本中的常见失败/警告项，并说明其真实含义和处理方式。

**文档版本**: 1.1  
**最后更新**: 2026-04-13  
**维护者**: req106-maintainer

---

## 当前判定口径

- `C2` 检查的是 **Python 可导入模块名**，当前要求：`requests`、`yaml`
- `D2` 检查的是 **HTML 中必需的数据块**，当前要求：`klineData`
- `realtimeData` 已降级为**可选块**，缺失时仅在详情里体现，不再判定失败
- `fund_flow_data.json` 为**预留数据文件**，当前主流程不再要求其存在

---

## 已知问题列表

### 问题 1: 运行时依赖缺失 [C2 - FAIL]

#### 症状

```text
[X] FAIL   | C2   | 必需库导入
Details: {"missing": ["requests"]}
```

或：

```text
[X] FAIL   | C2   | 必需库导入
Details: {"missing": ["yaml"]}
```

#### 根本原因

- 当前 Python 环境未安装主流程实际依赖
- `requests` 用于访问新浪财经 API
- `yaml`（来自 `PyYAML`）用于加载配置文件

#### 影响范围

- **影响模块**: `update_report.py`、`fix_ma_and_benchmark.py`、`realtime_data_updater.py`
- **功能影响**: 主流程无法稳定执行
- **系统是否可用**: 不可用或部分不可用

#### 解决方案

```bash
pip install requests pyyaml
```

#### 验证修复

```bash
python scripts/health_check.py --category C
```

预期看到：

```text
[OK] PASS   | C2   | 必需库导入
```

---

### 问题 2: 缺少必需的 klineData 块 [D2 - FAIL]

#### 症状

```text
[X] FAIL   | D2   | JavaScript 数据块
Details: {"required_missing": ["klineData"]}
```

#### 根本原因

- 根目录 `index.html` 未经过主更新流程刷新
- 或者 HTML 被旧版本/错误文件覆盖
- 或者手动编辑时误删了 `const klineData = {...}`

#### 影响范围

- **功能影响**: 图表主数据无法渲染
- **页面渲染**: 页面可能打开，但核心图表/表格不完整
- **系统是否可用**: 不可用

#### 解决方案

```bash
python scripts/update_report.py
```

#### 说明

- `realtimeData` 现在是可选块
- 即使 `realtimeData` 缺失，只要 `klineData` 正常，`D2` 仍会通过

#### 验证修复

```bash
python scripts/health_check.py --category D
```

---

### 问题 3: 数据时效性警告 [B5 - WARN]

#### 症状

```text
[!] WARN   | B5   | 数据时效性
Details: {"latest_date": "2026-04-11", "age_days": 2}
```

#### 根本原因

- 最新 K 线数据相对当前日期有延迟
- 周末、节假日或非交易时段出现该警告通常是正常现象

#### 影响范围

- **数据新鲜度**: 一般
- **图表显示**: 正常
- **系统可用性**: 完全可用

#### 解决方案

- 如果当前是交易日收盘后，重新执行：

```bash
python scripts/update_report.py
```

- 如果当前是周末或假期，可以暂不处理

---

## 问题汇总表

| ID | 问题 | 严重度 | 状态 | 解决难度 |
|----|------|--------|------|--------|
| C2 | 运行时依赖缺失 | 中 | ❌ FAIL | 低 |
| D2 | klineData 缺失 | 高 | ❌ FAIL | 低 |
| B5 | 数据时效性 | 低 | ⚠️ WARN | 低 |

---

## 快速排查顺序

1. 先跑完整检查：`python scripts/health_check.py`
2. 如果是 `C2`，先补依赖：`pip install requests pyyaml`
3. 如果是 `D2`，重跑主流程：`python scripts/update_report.py`
4. 如果只是 `B5`，结合交易日判断是否需要处理

---

**状态**: ✅ 已更新  
**最后测试**: 2026-04-13  
**下一步**: 随健康检查规则变更继续维护本文档
