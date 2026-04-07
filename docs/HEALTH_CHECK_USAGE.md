# ETF 系统健康检查使用指南

## 概述

`health_check.py` 是 ETF 报告系统的一键健康检查工具，用于验证系统的各个方面是否正常工作。

- **检查项数**: 25 项（6 大类别）
- **执行时间**: ~0.8 秒
- **输出格式**: 彩色终端表格、JSON、HTML（可选）

---

## 快速开始

### 基础检查

```bash
cd scripts/
python health_check.py
```

**输出示例**：
```
======================================================================
 ETF 系统健康检查 | 2026-04-07 16:38:30
======================================================================

[A] 文件完整性检查
----------------------------------------------------------------------
  [OK] PASS   | A1   | HTML 文件存在性
  [OK] PASS   | A2   | 数据文件完整性              | 3/3
  [OK] PASS   | A3   | 脚本文件完整性              | 5/5
  ...

总体状态: FAIL
检查项: 22/25 通过, 1 个警告, 2 个失败
检查时间: 0.8 秒
======================================================================
```

### 生成 JSON 报告

```bash
python health_check.py --json > health_check_baseline.json
```

保存为 JSON 格式便于程序化处理和历史对比。

---

## 命令行选项

| 选项 | 说明 | 示例 |
|------|------|------|
| `--json` | 输出 JSON 格式报告 | `python health_check.py --json` |
| `--html` | 输出 HTML 可视化报告 | `python health_check.py --html` |
| `--strict` | 严格模式（警告 = 失败） | `python health_check.py --strict` |
| `--category A,B,C` | 只检查特定类别 | `python health_check.py --category A,B` |
| `--verbose` | 详细日志输出 | `python health_check.py --verbose` |

### 选项说明

- **`--json`**: 输出纯 JSON 数据，便于集成到其他系统
- **`--html`**: 生成 HTML 报告，可用浏览器查看
- **`--strict`**: 启用严格模式，把 WARN 视为失败，返回码为 1
- **`--category`**: 指定类别（A/B/C/D/E/F），多个类别用逗号分隔
- **`--verbose`**: 输出详细日志，用于调试

---

## 返回码

| 返回码 | 含义 | 说明 |
|--------|------|------|
| 0 | PASS | 所有检查通过，无警告或失败 |
| 1 | WARN | 有警告但无失败（仅在 `--strict` 模式下为 1） |
| 2 | FAIL | 有失败项 |

### 使用示例

```bash
# 基础用法
python health_check.py
if [ $? -eq 0 ]; then
  echo "系统健康"
else
  echo "系统有问题"
fi

# 严格模式
python health_check.py --strict
if [ $? -ne 0 ]; then
  echo "检查失败或有警告"
fi
```

---

## 检查项详解

### A 类：文件完整性检查（5 项）

| ID | 项目 | 检查内容 | 常见问题 |
|----|------|--------|--------|
| A1 | HTML 文件存在性 | deploy/ 和 outputs/ 中的 index.html | 报告未生成或位置错误 |
| A2 | 数据文件完整性 | 3 个必需的 JSON 数据文件 | 缺少数据文件 |
| A3 | 脚本文件完整性 | 5 个核心脚本文件 | 脚本被删除或移动 |
| A4 | 文件大小合理性 | HTML > 500 KB, K线数据 > 100 KB | 数据异常或未更新 |
| A5 | 文件权限检查 | 文件可读、目录可写 | 权限问题（Windows 罕见） |

### B 类：数据有效性检查（6 项）

| ID | 项目 | 检查内容 | 常见问题 |
|----|------|--------|--------|
| B1 | JSON 解析有效性 | 数据文件能被正确解析 | JSON 格式错误 |
| B2 | ETF 代码完整性 | 包含全 6 支 ETF | 数据不完整 |
| B3 | K线数据结构 | 每个 ETF 有 daily 和 weekly | 数据结构不正确 |
| B4 | 日期一致性 | K线日期与实时数据一致 | 数据更新不同步 |
| B5 | 数据时效性 | 数据不超过 7 天陈旧 | ⚠️ 数据太旧（非交易日正常） |
| B6 | 成分股数据 | 每个 ETF 有 ≥ 5 个成分股 | 成分股数据缺失 |

### C 类：脚本依赖检查（5 项）

| ID | 项目 | 检查内容 | 常见问题 |
|----|------|--------|--------|
| C1 | Python 版本 | Python >= 3.8 | Python 版本过低 |
| C2 | 必需库导入 | requests, beautifulsoup4 | ❌ 库未安装 |
| C3 | 脚本导入链 | 核心模块可导入 | 模块有语法错误 |
| C4 | 外部 API 可达性 | 新浪财经 API 可访问 | ⚠️ 网络问题或 API 宕机 |
| C5 | 临时目录可写 | outputs/ 目录可写入文件 | 权限问题 |

### D 类：HTML 结构检查（4 项）

| ID | 项目 | 检查内容 | 常见问题 |
|----|------|--------|--------|
| D1 | HTML 标签平衡 | 所有标签正确配对 | HTML 代码有问题 |
| D2 | JavaScript 数据块 | klineData, realtimeData const | ❌ 数据块缺失 |
| D3 | ECharts CDN | 包含 ECharts 库 | 图表库未引入 |
| D4 | 样式 CSS 完整 | 关键 CSS 类存在 | 样式表缺失 |

### E 类：工作流逻辑检查（3 项）

| ID | 项目 | 检查内容 | 常见问题 |
|----|------|--------|--------|
| E1 | 事务管理 | .backups/ 目录有备份 | 备份功能异常 |
| E2 | 日期同步 | HTML 中的日期一致 | 日期更新失败 |
| E3 | 更新流程完整性 | 所有核心函数存在 | update_report.py 有问题 |

### F 类：系统配置检查（2 项）

| ID | 项目 | 检查内容 | 常见问题 |
|----|------|--------|--------|
| F1 | 成分股配置 | ETF_CONFIG 有 6 支 ETF | 配置不完整 |
| F2 | 基准指数配置 | 所有 ETF 基准设置正确 | 配置错误 |

---

## 解读报告

### 健康状态判断

- ✅ **PASS**（绿色 [OK]）: 检查通过
- ⚠️ **WARN**（黄色 [!]）: 警告，系统仍可用，建议关注
- ❌ **FAIL**（红色 [X]）: 失败，需要立即处理

### 整体状态

- **总体状态: PASS** → 系统完全健康
- **总体状态: WARN** → 有警告但可用（如 B5 数据老旧）
- **总体状态: FAIL** → 有失败项，需要修复（如 C2 库缺失）

### JSON 报告结构

```json
{
  "timestamp": "2026-04-07T16:38:46.840973",
  "overall_status": "FAIL",
  "total_checks": 25,
  "passed": 22,
  "warnings": 1,
  "failed": 2,
  "categories": { ... },
  "duration_seconds": 0.969,
  "environment": { ... }
}
```

---

## 常见问题

### Q1: C2 库缺失 (ImportError: No module named 'beautifulsoup4')

**症状**: 健康检查显示 C2 FAIL

**解决方案**:
```bash
pip install beautifulsoup4 lxml
```

### Q2: D2 realtimeData 块缺失

**症状**: HTML 中未找到 `const realtimeData = {...}`

**原因**: 实时数据更新器尚未执行

**解决方案**:
```bash
cd scripts/
python realtime_data_updater.py
python update_report.py
```

### Q3: B5 数据时效性警告

**症状**: `WARN | B5 | 数据时效性 | age_days: 4`

**原因**: 数据是 4 天前的（正常，因为在非交易日）

**解决方案**: 在下一个交易日收盘后运行 `update_report.py`

### Q4: C4 API 不可达

**症状**: `WARN | C4 | 外部 API 可达性`

**原因**: 新浪财经 API 网络问题或超时

**解决方案**: 检查网络连接，稍后重试

---

## 集成到自动化

### 与 update_report.py 集成

健康检查已自动集成到 `update_report.py` 的最后一步：

```bash
python update_report.py
```

输出会包含健康检查结果（Step 6）。

### 定时任务（Cron）

每个交易日 16:00 自动运行：

```cron
0 16 * * 1-5 cd /path/to/scripts && python health_check.py --json >> health_check_history.log
```

### 监控告警集成

```bash
#!/bin/bash
python health_check.py --json > report.json
failed_count=$(jq '.failed' report.json)

if [ "$failed_count" -gt 0 ]; then
  curl -X POST http://monitoring/alert \
    -d "ETF health check failed: $failed_count items"
fi
```

---

## 性能指标

| 指标 | 数值 |
|------|------|
| 总执行时间 | ~0.8 秒 |
| 检查项数 | 25 项 |
| 平均单项耗时 | 32 毫秒 |
| 最慢项 | C4 (API 连接) ~150ms |
| 最快项 | E2 (日期同步) ~5ms |

---

## 相关文档

- [`scripts/health_check.py`](../scripts/health_check.py) - 源代码
- [`scripts/HEALTH_CHECK_DESIGN.md`](../scripts/HEALTH_CHECK_DESIGN.md) - 设计文档
- [`docs/HEALTH_CHECK_KNOWN_ISSUES.md`](HEALTH_CHECK_KNOWN_ISSUES.md) - 已知问题
- [`scripts/update_report.py`](../scripts/update_report.py) - 集成位置

---

**最后更新**: 2026-04-07  
**版本**: 1.0  
**状态**: ✅ 完成
