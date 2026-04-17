# ETF 报告日更参数手册

## 目的

这份文档只回答一件事：**哪些内容需要日更，靠什么命令刷新，改动会落到哪里。**

默认从技能根目录执行：

```bash
python scripts/update_report.py
```

---

## 每日会刷新的内容

### 1. K 线数据

- **文件**: `data/etf_full_kline_data.json`
- **内容**: 日线、周线、MA 均线
- **触发方式**: `python scripts/update_report.py` → Step 1

### 2. 实时行情数据

- **文件**: `data/etf_realtime_data.json`
- **内容**: ETF 涨跌、成分股涨跌、交易量、时间戳
- **触发方式**: `python scripts/update_report.py` → Step 2 / Step 3

### 3. HTML 报告日期与页面数据

- **文件**: 根目录 `index.html`
- **内容**: 报告日期、数据截止、生成时间、页面数据块
- **触发方式**: `python scripts/update_report.py` → HTML 更新阶段

### 4. 解释层内容回填

- **来源**: `config/editorial_content.yaml`
- **页面结果**: 研究卡 / 宏观卡正文与逐条日期
- **触发方式**: `python scripts/update_report.py` 读取配置后统一回填

---

## 通常不需要频繁改的内容

### ETF 列表与基准指数

- **位置**: `config/config.yaml`
- **频率**: 按需
- **场景**: 换标的、调基准、调整 ETF 池

### API 配置

- **位置**: `config/config.yaml`
- **频率**: 按需
- **场景**: API 变更、限流调整

### 显示参数

- **位置**: `config/config.yaml`
- **频率**: 季度 / 半年级别
- **场景**: 调整显示区间、均线预热期、视觉参数

---

## 日常维护节奏

| 频率 | 操作 | 命令 |
|------|------|------|
| 每天 | 刷新报告主流程 | `python scripts/update_report.py` |
| 每周 | 跑健康检查 | `python scripts/health_check.py` |
| 按需 | 审查目录卫生 | `python scripts/audit_project.py --quick` |

---

## 影响路径

```text
config/*.yaml / data/*.json
        ↓
python scripts/update_report.py
        ↓
根目录 index.html + logs/*.jsonl
```

---

## 最佳实践

- **一次性输出**：统一放 `_working/`
- **正式运行数据**：只留在 `data/`、`logs/`、`.backup/`
- **根目录**：只保留源码、文档和主报告 `index.html`
- **健康检查基线**：需要时用 `python scripts/health_check.py --json > _working/xxx.json`

---

**最后更新**: 2026-04-17
