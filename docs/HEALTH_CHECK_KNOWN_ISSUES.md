# ETF 系统健康检查 - 已知问题和解决方案

## 概述

本文档记录 REQ-106 健康检查发现的已知问题、其根本原因和解决方案。

**文档版本**: 1.0  
**最后更新**: 2026-04-07  
**维护者**: req106-impl

---

## 已知问题列表

### 问题 1: beautifulsoup4 库缺失 [C2 - FAIL]

#### 症状
```
[X] FAIL   | C2   | 必需库导入
Details: {"missing": ["beautifulsoup4"]}
```

#### 根本原因

- beautifulsoup4 库在当前 Python 环境中未安装
- 虽然 `bs4` 包可以导入，但 `beautifulsoup4` 元包缺失
- 这会导致某些依赖项无法正确加载

#### 影响范围

- **影响模块**: update_report.py（数据处理）
- **功能影响**: 可能导致 HTML 解析失败
- **系统是否可用**: 部分功能受影响

#### 解决方案

**方案 A: 使用 pip 安装（推荐）**

```bash
# Windows PowerShell
pip install beautifulsoup4 lxml

# 验证安装
python -c "import bs4; from bs4 import BeautifulSoup; print('OK')"
```

**方案 B: 使用 requirements.txt**

```bash
pip install -r requirements.txt
```

#### 验证修复

执行健康检查确认问题已解决：

```bash
python health_check.py --category C

# 预期输出:
# [OK] PASS   | C2   | 必需库导入
```

#### 预防措施

- 在项目根目录维护 `requirements.txt`
- 新项目启动时首先运行 `pip install -r requirements.txt`
- 定期运行健康检查检测依赖问题

---

### 问题 2: realtimeData 块缺失 [D2 - FAIL]

#### 症状

```
[X] FAIL   | D2   | JavaScript 数据块
Details: {"missing": ["realtimeData"]}
```

#### 根本原因

- HTML 文件中缺少 `const realtimeData = {...}` JavaScript 常量
- 这通常发生在：
  1. 首次生成报告时（未运行 realtime_data_updater.py）
  2. 实时数据更新流程被跳过
  3. 数据更新失败但 HTML 生成继续

#### 影响范围

- **功能影响**: ETF 实时涨跌幅无法显示
- **页面渲染**: 图表可显示但无成分股数据
- **系统是否可用**: 主要功能可用，但数据不完整

#### 解决方案

**步骤 1: 运行实时数据更新器**

```bash
cd scripts/
python realtime_data_updater.py
```

**预期输出示例**:
```
[INFO] 开始获取实时数据...
[INFO] 处理 ETF 512400...
[INFO] 获取成分股...
[INFO] 数据已保存到 ../data/etf_realtime_data.json
```

**步骤 2: 运行完整报告更新**

```bash
python update_report.py
```

这会执行完整的更新流程，包括数据生成和 HTML 更新。

**步骤 3: 验证修复**

```bash
python health_check.py --category D

# 预期输出:
# [OK] PASS   | D2   | JavaScript 数据块
```

#### 快速修复

如果问题已解决，可以直接运行一体化更新：

```bash
python update_report.py --full
```

#### 预防措施

- 总是通过 `update_report.py` 而不是手动编辑 HTML
- 定期运行健康检查检测结构问题
- 在自动化脚本中添加健康检查验证步骤

#### 根本原因分析

如果重复出现此问题，检查以下项：

```bash
# 1. 检查数据文件是否存在
ls -la ../data/etf_realtime_data.json

# 2. 检查 update_report.py 的相关代码
grep -n "realtimeData" update_report.py

# 3. 查看更新日志
grep "ERROR\|realtimeData" logs/update_report.log
```

---

### 问题 3: 数据时效性警告 [B5 - WARN]

#### 症状

```
[!] WARN   | B5   | 数据时效性
Details: {"latest_date": "2026-04-03", "age_days": 4}
```

#### 根本原因

- 最新 K线数据是 2026-04-03（周五）
- 当前日期是 2026-04-07（周二）
- 数据相隔 4 天，超过 2 天阈值但不超过 7 天失败阈值

#### 原因解析

**正常原因**（不需要处理）:
- 周末不交易（2026-04-04、2026-04-05）
- 可能是法定假期
- 交易量较小导致数据更新延迟

**异常原因**（需要处理）:
- 数据更新脚本未运行
- API 源数据过期
- 网络连接问题导致更新失败

#### 影响范围

- **数据新鲜度**: 低（但可接受）
- **图表显示**: 正常（显示最新可用数据）
- **系统可用性**: 完全可用

#### 判断是否需要处理

运行以下检查确认是否为正常情况：

```bash
# 1. 检查当前日期是否为交易日
date  # 查看当前日期

# 2. 检查最新数据的日期
python -c "import json; d=json.load(open('../data/etf_full_kline_data.json')); \
  print(list(d.values())[0]['daily']['dates'][-1])"

# 3. 如果当前为交易日后，应该更新数据
python update_report.py
```

#### 解决方案

**方案 A: 手动更新（立即）**

```bash
cd scripts/
python update_report.py
```

这会：
1. 获取最新 K线数据
2. 更新 HTML 中的数据块
3. 重新运行健康检查

**方案 B: 确认是非交易日（推迟）**

如果当前是周末或假期，警告为正常，无需处理。等待下一交易日后再运行更新。

**方案 C: 设置自动定时更新**

在 crontab 中添加定时任务（每个交易日 16:00）：

```bash
0 16 * * 1-5 cd /path/to/scripts && python update_report.py >> logs/auto_update.log 2>&1
```

#### 预期行为

按时间线预期的 B5 检查结果：

| 时间 | 数据日期 | 距离天数 | B5 状态 |
|------|---------|--------|--------|
| 交易日 16:00 | 当天 | 0 天 | ✅ PASS |
| 交易日+1 | 昨天 | 1 天 | ✅ PASS |
| 交易日+2 | 2 天前 | 2 天 | ⚠️ WARN |
| 交易日+7 | 7 天前 | 7 天 | ❌ FAIL |
| 交易日+8+ | 8+ 天前 | > 8 天 | ❌ FAIL |

#### 预防措施

- 配置自动定时更新任务
- 定期监控 B5 状态
- 在大盘波动期间增加更新频率

---

## 问题汇总表

| ID | 问题 | 严重度 | 状态 | 解决难度 |
|----|------|--------|------|--------|
| C2 | beautifulsoup4 缺失 | 中 | ❌ FAIL | 低 (一行命令) |
| D2 | realtimeData 缺失 | 中 | ❌ FAIL | 低 (脚本) |
| B5 | 数据时效性 | 低 | ⚠️ WARN | 低 (自动) |

---

## 故障排查流程

### 快速诊断

```bash
cd scripts/

# 1. 运行完整检查
python health_check.py

# 2. 查看 FAIL 项
python health_check.py --json | jq '.[] | select(.status=="FAIL")'

# 3. 查看详细错误
python health_check.py --verbose

# 4. 按类别检查
python health_check.py --category C  # 检查依赖
python health_check.py --category D  # 检查 HTML
```

### 按问题类型排查

**如果是 C 类问题（依赖）**:
```bash
# 检查 Python 环境
python -c "import sys; print(sys.executable)"

# 检查库
pip list | grep -E "beautifulsoup4|requests|lxml"

# 安装缺失的库
pip install beautifulsoup4 lxml
```

**如果是 D 类问题（HTML 结构）**:
```bash
# 检查 HTML 完整性
python verify_html_integrity.py ../outputs/index.html

# 重新生成 HTML
python realtime_data_updater.py
python update_report.py
```

**如果是 B 类问题（数据）**:
```bash
# 检查数据文件
ls -lh ../data/

# 检查数据内容
python -c "import json; print(json.dumps(json.load(open('../data/etf_full_kline_data.json')), indent=2)[:500])"

# 更新数据
python fix_ma_and_benchmark.py
python realtime_data_updater.py
```

---

## 联系与支持

- **设计文档**: [`scripts/HEALTH_CHECK_DESIGN.md`](../scripts/HEALTH_CHECK_DESIGN.md)
- **使用指南**: [`docs/HEALTH_CHECK_USAGE.md`](HEALTH_CHECK_USAGE.md)
- **源代码**: [`scripts/health_check.py`](../scripts/health_check.py)

---

**状态**: ✅ 已验证  
**最后测试**: 2026-04-07  
**下一步**: 定期监控新问题，更新此文档
