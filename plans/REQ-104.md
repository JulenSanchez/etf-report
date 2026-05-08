# REQ-104 集成改造快速指南

**快速概览**：本文档提供 logger 系统集成的代码示例和改造清单。

---

## 快速开始

### 1. 导入和初始化

在每个脚本的顶部添加：

```python
from logger import Logger

# 创建 logger 实例（在 main() 或脚本开始时）
logger = Logger(name="script_name", level="INFO", file_output=True)
```

### 2. 替换 print() 调用

#### 例 1：简单消息
```python
# 原来
print("[OK] 读取数据成功")

# 改为
logger.info("读取数据成功")
```

#### 例 2：带上下文的消息
```python
# 原来
print(f"[OK] 读取K线数据: {kline_file}")

# 改为
logger.info("读取K线数据", {"file": kline_file})
```

#### 例 3：错误处理
```python
# 原来
except Exception as e:
    print(f"[ERROR] 获取数据失败: {e}")

# 改为
except Exception as e:
    logger.error("获取数据失败", {"error": str(e), "retry": 3})
```

#### 例 4：日志级别转换
```
[OK]     → logger.info()
[WARN]   → logger.warn()
[ERROR]  → logger.error()
（无标记) → logger.debug() 或 logger.info()
```

---

## 文件改造清单

### ✅ 已完成

- [x] `scripts/logger.py` - 日志系统框架（**已实现**）

### ⏳ 待改造（按优先级）

#### 🔴 P1 优先级

- [ ] **`update_report.py`** (41 个 print)
  - 改造 `print_header()`, `print_step()` 替换为 logger 调用
  - 替换所有 print(f"[OK]..."), print(f"[ERROR]...")
  - 替换步骤分隔输出

- [ ] **`realtime_data_updater.py`** (32 个 print)
  - 改造 ETF 循环中的 print() 调用
  - 替换成分股处理的日志

- [ ] **`fix_ma_and_benchmark.py`** (25 个 print)
  - 改造 K线数据获取的日志
  - 记录均线计算结果

- [ ] **`transaction.py`** (20 个 print)
  - 改造备份/恢复操作的日志
  - 在 TransactionManager 中集成 logger

#### 🟠 P2 优先级

- [ ] **`verify_html_integrity.py`** (8 个 print)
  - 可选改造（验证脚本，日志较少）

---

## 改造工作流

### Step 1: 添加 logger 导入

在文件顶部（所有其他导入之后）添加：

```python
from logger import Logger

# 日志初始化（通常在 main() 或脚本入口）
logger = Logger(
    name="script_name",      # 使用脚本名称
    level="INFO",            # 显示 INFO 及以上级别
    file_output=True,        # 输出到 logs/ 目录
)
```

### Step 2: 批量查找替换

用编辑器的查找替换功能（Ctrl+H）：

**替换模式 1**：`print(f"[OK] ` → （手动查看并改为 logger.info）
**替换模式 2**：`print(f"[ERROR]` → （手动查看并改为 logger.error）
**替换模式 3**：`print(f"[WARN]` → （手动查看并改为 logger.warn）

### Step 3: 逐个检查

```python
# 原代码例子
print(f"  [OK] 更新klineData (6支ETF的K线数据)")

# 改造后
logger.info("更新klineData", {
    "etf_count": 6,
    "description": "K线数据"
})

# 或者简化为
logger.info("更新klineData完成", {"etf_count": 6})
```

### Step 4: 验证

运行脚本并检查：
1. 控制台输出是否正确（带颜色和时间戳）
2. `logs/` 目录是否生成了 JSONL 文件
3. JSONL 文件内容是否为有效的 JSON

```bash
# 检查日志文件
cat "c:/path/to/logs/update_report_20260407.jsonl" | head -5
```

---

## 改造示例（完整）

### 示例 1：update_report.py 中的函数改造

**改造前**：
```python
def print_header(title):
    """打印分隔标题"""
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)

def run_kline_update():
    """执行K线数据更新"""
    print_step(1, "获取K线数据并更新JS")
    try:
        import fix_ma_and_benchmark
        fix_ma_and_benchmark.main()
        return True
    except Exception as e:
        print(f"[ERROR] K线数据更新失败: {e}")
        import traceback
        traceback.print_exc()
        return False
```

**改造后**：
```python
def run_kline_update():
    """执行K线数据更新"""
    logger.info("=" * 60)
    logger.info("Step 1: 获取K线数据并更新JS")
    logger.info("=" * 60)
    
    try:
        import fix_ma_and_benchmark
        fix_ma_and_benchmark.main()
        logger.info("K线数据更新成功")
        return True
    except Exception as e:
        logger.error("K线数据更新失败", {"error": str(e)})
        import traceback
        traceback.print_exc()
        return False
```

### 示例 2：realtime_data_updater.py 中的循环改造

**改造前**：
```python
for etf_code, config in ETF_CONFIG.items():
    print(f"\n[ETF] {etf_code} {config['name']}")
    
    etf_symbol = f"{config['market']}{etf_code}"
    all_symbols = [etf_symbol] + holding_symbols
    quotes = fetch_realtime_quote_sina(all_symbols)
    
    etf_quote = quotes.get(etf_symbol, {})
    etf_change = etf_quote.get('change_pct', 0)
    print(f"  -> ETF涨跌幅: {etf_change:+.2f}%")
    
    for h in config['holdings']:
        symbol = f"{h['market']}{h['code']}"
        quote = quotes.get(symbol, {})
        change = quote.get('change_pct', None)
        if change is not None:
            print(f"  -> {h['name']}: {change:+.2f}%")
```

**改造后**：
```python
for etf_code, config in ETF_CONFIG.items():
    logger.info("开始处理ETF", {
        "code": etf_code,
        "name": config['name']
    })
    
    etf_symbol = f"{config['market']}{etf_code}"
    all_symbols = [etf_symbol] + holding_symbols
    quotes = fetch_realtime_quote_sina(all_symbols)
    
    etf_quote = quotes.get(etf_symbol, {})
    etf_change = etf_quote.get('change_pct', 0)
    logger.info("ETF行情获取", {
        "code": etf_code,
        "change_pct": etf_change
    })
    
    for h in config['holdings']:
        symbol = f"{h['market']}{h['code']}"
        quote = quotes.get(symbol, {})
        change = quote.get('change_pct', None)
        if change is not None:
            logger.debug("成分股涨跌", {
                "stock_name": h['name'],
                "change_pct": change
            })
```

---

## 日志输出效果

### 控制台输出示例

```
[2026-04-07T15:25:30.123456] INFO - 开始处理ETF
  Context:
    {
      "code": "512400",
      "name": "有色金属ETF"
    }

[2026-04-07T15:25:31.456789] INFO - ETF行情获取
  Context:
    {
      "code": "512400",
      "change_pct": 2.5
    }

[2026-04-07T15:25:32.789012] ERROR - K线数据更新失败
  Context:
    {
      "error": "Connection timeout",
      "retry": 3
    }
```

### 日志文件示例

**文件**：`logs/update_report_20260407.jsonl`

```jsonl
{"timestamp":"2026-04-07T15:25:30.123456","logger":"update_report","level":"INFO","message":"开始处理ETF","context":{"code":"512400","name":"有色金属ETF"}}
{"timestamp":"2026-04-07T15:25:31.456789","logger":"update_report","level":"INFO","message":"ETF行情获取","context":{"code":"512400","change_pct":2.5}}
{"timestamp":"2026-04-07T15:25:32.789012","logger":"update_report","level":"ERROR","message":"K线数据更新失败","context":{"error":"Connection timeout","retry":3}}
```

---

## 常见问题

### Q1: 是否需要修改现有函数的逻辑？
**A**: 完全不需要。只改变输出方式，业务逻辑保持 100% 不变。

### Q2: 是否需要删除现有的 `print_header()` 和 `print_step()` 函数？
**A**: 不需要。可以保留作为参考，或逐步重构为使用 logger 的版本。

### Q3: 如何处理 `traceback.print_exc()` 的调用？
**A**: 保留 `traceback.print_exc()` 不变（用于调试），logger 在上面记录错误摘要。

### Q4: 日志文件会无限增长吗？
**A**: 按天生成，每天一个 JSONL 文件。可手动或自动清理旧日志。

### Q5: 性能影响有多大？
**A**: 非常小。主要是网络 I/O（获取 API 数据）是瓶颈，日志 I/O 几乎可以忽略。

---

## 改造检查清单

在改造每个文件前，使用以下清单：

```
[ ] 1. 导入 Logger 类
[ ] 2. 在 main() 或入口处初始化 logger 实例
[ ] 3. 替换所有 print(f"[OK] ...") → logger.info()
[ ] 4. 替换所有 print(f"[ERROR] ...") → logger.error()
[ ] 5. 替换所有 print(f"[WARN] ...") → logger.warn()
[ ] 6. 替换所有其他 print() → logger.info() 或 logger.debug()
[ ] 7. 提取上下文信息添加到第二个参数
[ ] 8. 运行脚本验证输出
[ ] 9. 检查 logs/ 目录是否生成 JSONL 文件
[ ] 10. 用文本编辑器打开 JSONL 文件验证格式
```

---

## 下一步

1. 参考 `REQ-104_ANALYSIS.md` 了解详细的设计和统计
2. 从 P1 优先级的文件开始改造
3. 逐文件验证后合并提交
4. 运行完整的报告更新流程测试

**预计总工作量**：2-3 小时（包括改造、测试、验证）

---

**最后更新**：2026-04-07 15:25
