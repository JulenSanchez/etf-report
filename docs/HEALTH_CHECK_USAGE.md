# ETF 系统健康检查使用指南

## 概述

`health_check.py` 用于快速验证 `etf-report` 当前目录、数据、HTML、工作流和配置是否处于可运行状态。

- **检查项数**: 26 项（6 大类别，含解释层鲜度检查）
- **默认入口**: `python scripts/health_check.py`
- **常见输出**: 终端彩色表格；可选 JSON / HTML
- **目录约定**: 一次性导出建议写到 `_working/`

---

## 快速开始

### 基础检查

```bash
python scripts/health_check.py
```

### 生成 JSON 报告

```bash
python scripts/health_check.py --json > _working/health_check_baseline.json
```

### 常用变体

```bash
python scripts/health_check.py --strict
python scripts/health_check.py --category E
python scripts/health_check.py --html
```

---

## 命令行选项

| 选项 | 说明 | 示例 |
|------|------|------|
| `--json` | 输出 JSON 格式报告 | `python scripts/health_check.py --json` |
| `--html` | 输出 HTML 可视化报告 | `python scripts/health_check.py --html` |
| `--strict` | 严格模式（警告 = 失败） | `python scripts/health_check.py --strict` |
| `--category A,B,C` | 只检查特定类别 | `python scripts/health_check.py --category A,B` |
| `--verbose` | 输出详细日志 | `python scripts/health_check.py --verbose` |

---

## 返回码

| 返回码 | 含义 | 说明 |
|--------|------|------|
| 0 | PASS | 无警告、无失败 |
| 1 | WARN | 仅在 `--strict` 模式下，警告会返回 1 |
| 2 | FAIL | 存在失败项 |

---

## 检查项结构

### A 类：文件完整性（5 项）
- `A1`: 根目录 `index.html` 是否存在
- `A2`: `data/` 下 2 个必需 JSON 是否存在
- `A3`: 5 个核心脚本是否存在
- `A4`: HTML / K 线数据体积是否异常偏小
- `A5`: 主 HTML 目录与关键文件是否可读写

### B 类：数据有效性（6 项）
- `B1`: JSON 可解析
- `B2`: ETF 代码完整
- `B3`: K 线结构完整
- `B4`: 日期可提取
- `B5`: 数据时效性
- `B6`: 成分股数据数量

### C 类：脚本依赖（5 项）
- `C1`: Python 版本
- `C2`: `requests` / `yaml` 导入
- `C3`: 核心脚本导入链
- `C4`: 新浪财经 API 可达性
- `C5`: 技能根目录临时探针写入能力

### D 类：HTML 结构（4 项）
- `D1`: HTML 标签平衡
- `D2`: 必需数据块（`klineData`）存在；`realtimeData` 为可选块
- `D3`: ECharts 引入存在
- `D4`: 关键样式类存在

### E 类：工作流逻辑（4 项）
- `E1`: `.backup/` 事务快照目录状态
- `E2`: HTML 日期同步
- `E3`: `update_report.py` 主流程函数完整性
- `E4`: 解释层鲜度（按 `freshness_policy` 校验）

### F 类：系统配置（2 项）
- `F1`: ETF 成分股配置完整性
- `F2`: 基准指数配置正确性

---

## 常见问题

### Q1: D2 缺少 `klineData`

**原因**: 页面未经过主流程刷新，或 HTML 被旧文件覆盖。

**处理**:

```bash
python scripts/update_report.py
```

### Q2: B5 数据时效性出现 WARN

**原因**: 非交易日或最新数据尚未刷新，常见于周末 / 节假日。

**处理**: 在下一个交易日收盘后重新运行 `python scripts/update_report.py`。

### Q3: E4 解释层鲜度出现 WARN / FAIL

**原因**: `config/editorial_content.yaml` 中的 `content_date` 与 `freshness_policy` 不匹配。

**处理**:
- 日更内容优先使用 `manual_daily`
- 编辑态内容可用 `sticky`
- 修正后重新运行主流程

### Q4: C2 库缺失

```bash
pip install requests pyyaml
```

---

## 与主流程集成

主流程 `python scripts/update_report.py` 末尾会自动执行健康检查，并把摘要写入终端与结构化日志。

如需单独留一份 JSON 基线：

```bash
python scripts/health_check.py --json > _working/health_check_latest.json
```

---

## 自动化示例

### 定时任务（概念示例）

```cron
0 16 * * 1-5 python /path/to/etf-report/scripts/health_check.py --json > /path/to/etf-report/_working/health_check_latest.json
```

### 本地巡检

```bash
python scripts/health_check.py --category E
python scripts/health_check.py --json > _working/report.json
```

---

## 相关文档

- [`scripts/health_check.py`](../scripts/health_check.py)
- [`scripts/update_report.py`](../scripts/update_report.py)
- [`WORKFLOW.md`](../WORKFLOW.md)
- [`HEALTH_CHECK_KNOWN_ISSUES.md`](HEALTH_CHECK_KNOWN_ISSUES.md)

---

**最后更新**: 2026-04-17  
**版本**: 1.1  
**状态**: ✅ 完成
