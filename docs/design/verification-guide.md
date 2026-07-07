# 验证武器库 — AI 自验证方法论

> **读者**: AI Agent。本文不是给人看的测试文档，是给 AI 在开发完成后**自行设计验证方案**的武器目录。
>
> **核心原则**: 写完代码 ≠ 做完需求。验证通过才算做完。

---

## 一、验证总则

### 1.1 何时验证

- **改核心逻辑后** → 必须验证（回测引擎、数据管线、因子计算、清洗逻辑、参数契约）
- **改配置/常量后** → 必须验证（时间、阈值、默认值、计划任务）
- **改前端后** → 必须验证（布局、交互、数据绑定、图表）
- **改输出格式后** → 必须验证（推送内容、表格、Markdown）

### 1.2 验证通过标准

禁止以下"假通过"：

| ❌ 不算通过 | ✅ 必须满足 |
|------------|-----------|
| "日志没报错" | 日志中出现**预期的关键字段**（如 `status: confirmed`、`post-market`） |
| "status=ok" | 检查**下游产物**是否正确（CSV 有当日行、回测结果数值在预期范围） |
| "环境因素导致的失败" | 设计**不依赖环境的替代验证**，或标记为"用户协助验证" |
| "代码看起来正确" | 实际执行并检查输出 |
| "之前跑通过" | 每次改动后重新验证 |

### 1.3 武器选择原则

1. **能用最小化就不用全流程** — 测一个函数比跑整个管线快
2. **能用构造数据就不用真实数据** — 假数据可控、可复现
3. **能用比率检查就不用绝对值** — 比率对数据漂移鲁棒
4. **AI 做不了的明确标记** — 让用户协助，不假装能验证

---

## 二、场景 → 武器映射表

### 场景 A：时间/调度变更

**典型需求**: 改计划任务时间、改冷却期、改触发条件  
**历史案例**: REQ-348（14:50→15:10）、BUG-040（端口冲突）

| 武器 | 适用情况 | 操作 | 示例 |
|------|---------|------|------|
| **时间 Mock** | 逻辑依赖 `datetime.now()` 或时间判断函数 | 临时改常量或 monkey-patch | `COOL_OFF_TIME = 0` 模拟盘后；`_is_post_market()` return True |
| **时钟推进** | 需要验证"时间点 A 行为≠时间点 B" | 在脚本中注入假时间，分两次跑 | 设置 `_now = datetime(2026,7,6,14,50)` vs `15,10` 对比 |
| **隔离验证** | 测试后需恢复数据 | 清数据→跑→恢复 | REQ-348 验证：删 CSV 当日行→跑 preclose_push→重拉数据恢复 |
| **用户协助** | 计划任务实际触发、微信推送 | 明确告知用户验证步骤 | "请在 15:10 后检查微信是否收到推送，标题是否不含'收盘前'" |

**关键验证点**:
- 新时间点行为是否正确（走 intraday 还是 post-market？）
- CSV 是否写入当日数据？
- 推送内容是否使用正确的数据源？

### 场景 B：数据管线变更

**典型需求**: 改 CSV 写入逻辑、改 intraday cache、改日期逻辑、改拆股清洗  
**历史案例**: REQ-354（拆股自愈）、BUG-041（盘中不含今日数据）、BUG-028（分页丢数据）

| 武器 | 适用情况 | 操作 | 示例 |
|------|---------|------|------|
| **数据构造** | 需要特定数据状态来验证逻辑 | 手工构造 CSV 行或 cache 条目 | 构造 CSV 末笔 close=1.58 + intraday close=0.76 来触发清洗 |
| **边界注入** | 验证边界条件处理 | 造极端/缺失数据 | 空 intraday_cache、CSV 缺最后一日、跨周末 gap |
| **快照对比** | 改数据清洗逻辑 | 改前保存一份数据，改后对比 | `df.equals(before_df)` |
| **比率检查** | 验证数据变换正确性 | 计算变换前后比率 | csv_close / rt_close ≈ split_ratio → 触发清洗；≈1.0 → 跳过 |
| **CSV 内容验证** | 验证文件写入 | 直接读 CSV 检查特定行列 | `pd.read_csv` → 检查 date 列是否有今日、close 值是否在预期范围 |
| **全量对账** | 改数据拉取逻辑 | 对比新旧拉取结果 | 同一 ETF 新旧函数各拉一次，diff 字段 |

**关键验证点**:
- CSV 是否含当日行？（`grep $(date +%Y-%m-%d) data/quant/*_daily.csv`）
- CSV 数据是否正确？（close 值量级是否合理）
- 边界条件：空数据、缺日、停牌、拆股当天

### 场景 C：回测引擎变更

**典型需求**: 改因子计算、仓位分配、融资利息、杠杆  
**历史案例**: REQ-339（融资利息）、BUG-038（杠杆从未生效）、BUG-024（set 顺序不确定）、BUG-025（lookahead bias）、BUG-026（残量回收超上限）

| 武器 | 适用情况 | 操作 | 示例 |
|------|---------|------|------|
| **参数扫描** | 验证逻辑对参数的响应 | 极端值代入 | rate=0 → AR 应不变；rate=0.5 → AR 应大幅下降 |
| **退化到基线** | 新逻辑有"关闭"开关 | 设新参数=0/None，断言结果=旧基线 | `financing_rate=0` → 回测结果与改前完全一致 |
| **快照对比** | 改公式但不改变行为 | 改前后跑同一 preset | `nav["nav"].iloc[-1]` 差值 < 0.01% |
| **不变性检查** | 验证某些量不应被改动影响 | 检查 invariant | 加融资利息后 `cash >= -total_exposure`（不会穿仓） |
| **最小化回测** | 快速验证 | 缩小窗口 | `start="2025-06-01", end="2025-09-01"` 代替 6Y |
| **已知答案测试** | 验证计算正确性 | 手算一笔，对比引擎输出 | 持仓 2 支各 50%，本金 100w → 每支 50w → 除以现价得股数 |
| **确定性检查** | 验证结果可复现 | 同参数跑两次 | `result_1 == result_2`（需先确认 PYTHONHASHSEED） |

**关键验证点**:
- 结果是否可复现？（同参数两次跑一致）
- 极端参数下是否合理？（rate=0、leverage=1.0、band=0）
- 不变性是否保持？（仓位和=100%、现金不会 < 合理下限）

### 场景 D：算法/参数变更

**典型需求**: 改分数带、改参数边界、改默认值、改公式  
**历史案例**: REQ-310（动态分数带）、BUG-042（AR 公式错误）、BUG-044（去杠杆反向放大）

| 武器 | 适用情况 | 操作 | 示例 |
|------|---------|------|------|
| **退化到基线** | 新参数有"关闭"值 | 设 band_sensitivity=0，断言 = 静态 band | BS=0 → 有效 B ≡ B |
| **参数扫描** | 验证公式单调性/方向 | 取 3 个值（低/中/高） | band=0/0.03/0.08 跑回测，检查 AR 是否倒 U |
| **反向验证** | 验证公式本身正确 | 从输出反推输入 | 已知有效 B，反推 trend，检查是否在合理范围 |
| **边界检查** | 验证 clamp/floor/ceiling | 输入极端值 | trend=+100 → band 应 clamp 到 floor；trend=-100 → ceiling |
| **全链路审计** | 改参数名/默认值 | 按 AGENTS.md 审计链逐层检查 | PARAM_SCHEMA → PARAM_BOUNDS → defaults.yaml → ... |
| **公式单元测试** | 验证纯函数 | 构造输入→断言输出 | `dynamic_band(B=0.03, BS=0.03, trend=0.3) == 0.021` |

**关键验证点**:
- 关闭新参数 = 旧行为
- 极端输入不越界（clamp 生效）
- 全链路：参数名/默认值在每一层一致

### 场景 E：前端 UI 变更

**典型需求**: 改 HTML/CSS/JS、图表、控件、布局  
**历史案例**: REQ-343（进度条）、BUG-035（翻页高度跳动）、BUG-036（按钮无响应）、BUG-037（图表缩放不联动）、BUG-039（ECharts 清空子元素）

| 武器 | 适用情况 | 操作 | 示例 |
|------|---------|------|------|
| **浏览器验证** | 任何 UI 改动 | 刷新页面检查效果 | 改 `tuner.html` → 用户 F5 刷新（无需重启 Tuner） |
| **JS 语法检查** | 改 JavaScript | Node.js 快速语法检查 | `node -c tuner.html` 或检查 `</script>` 是否匹配 |
| **DOM 断言** | 验证元素存在/属性正确 | 浏览器 F12 Console 执行 | `$id('frontier-wrap-gambler').style.display` 应为 `'none'` |
| **CSS 变量检查** | 改配色 | 检查所有 var() 引用的变量是否已定义 | grep `var(--` 在 HTML 中，确认在 `:root` 中有定义 |
| **交互测试** | 点击/展开/切换 | 模拟用户操作序列 | 点击展开→检查箭头方向→再点折叠→检查箭头恢复 |
| **多分辨率** | 布局改动 | 改变浏览器宽度 | 1024px / 1440px / 1920px |
| **用户协助** | AI 无法渲染浏览器 | 明确告知检查项 | "请 F12 打开 Console，检查是否有红色报错；点击展开按钮，检查箭头方向" |

**关键验证点**:
- 不改 HTML 时不需要重启 Tuner（直接刷新浏览器）
- ECharts 图表：`echarts.init()` 会清空容器，不要把其他元素放在图表容器内
- JS 中 `onclick="..."` 属性内的引号嵌套——`JSON.stringify` 含双引号会截断

### 场景 F：输出格式变更

**典型需求**: 改推送内容、表格格式、Markdown 输出  
**历史案例**: REQ-353（调仓执行表）、REQ-300（合成杠杆摘要）

| 武器 | 适用情况 | 操作 | 示例 |
|------|---------|------|------|
| **--output-md** | 推送类改动 | 输出到文件而非推送 | `python scripts/preclose_push.py --output-md` → 检查 Desktop 上的文件 |
| **字段逐项检查** | 表格/结构改动 | 对照需求文档逐项核对 | 执行表：金额是否正确 × 仓位%？股数是否取整到 100？ |
| **Golden file** | 输出格式稳定后 | 保存正确输出，后续 diff | `diff Desktop/old.md Desktop/new.md` |
| **边界计算** | 数值计算类 | 手算一笔对比 | 50w × 58% = 29w，29w / 1.234 = 235,007 → floor 到 235,000 |

**关键验证点**:
- 用 `--output-md` 代替真实推送进行测试
- 金额 = 总资金 × 仓位%，股数 = floor(金额 / 现价 / 100) × 100
- 零仓位 ETF 不应出现

### 场景 G：架构迁移

**典型需求**: 脚本→src、模块拆分、重命名  
**历史案例**: REQ-334（scripts→src 迁移）

| 武器 | 适用情况 | 操作 | 示例 |
|------|---------|------|------|
| **Import 检查** | 模块移动 | 逐个 import 新路径 | `python -c "from etf_report.core.xxx import yyy"` |
| **回归测试** | 等价迁移 | 跑全部已有测试 | `pytest tests/ -x` |
| **API 不变性** | 对外接口不变 | 旧调用方式仍可用 | 旧 `from scripts.quant_backtest import run_backtest` 应有 deprecation warning 而非报错 |
| **diff 范围检查** | 纯移动 | 确认 diff 只有 import 路径变化 | `git diff --stat` 应该只改路径，逻辑行不变 |

---

## 三、武器详解

### 3.1 时间 Mock

**原理**: 不等待真实时间，用假时间触发特定代码路径。

**方法 1: 改常量**（最简单，适合快速验证）

```python
# 场景: 验证 15:10 后的 post-market 路径
# 当前真实时间是 11:00（盘中），但我们需要模拟盘后行为

# 在测试脚本中临时把冷却期设为 0:
COOL_OFF_TIME = 0  # 原值 910（15:10），改为 0 → _is_post_market() 立即返回 True

# 然后调用目标函数:
result = refresh_data(config)
# 此时即使真实时间是早上，也会走 post-market 路径写 CSV

# 验证完成后恢复原值
COOL_OFF_TIME = 910
```

**方法 2: Monkey-patch**（不改源码，适合测试脚本）

```python
# 文件: temp_scripts/verify_post_market.py
import quant_tuner as qt
from datetime import datetime

# ── 注入假时间 ──
original_cool_off = qt.COOL_OFF_TIME
qt.COOL_OFF_TIME = 0  # 模拟盘后

# 执行验证
result = qt.refresh_data(qt.CACHE.get("cfg"))
print(f"Status: {result.get('status')}")  # 预期: "confirmed"（post-market）
print(f"CSV rows after: ...")  # 检查 CSV 是否有当日行

# ── 恢复 ──
qt.COOL_OFF_TIME = original_cool_off
```

**方法 3: 注入假 datetime**（适合测试时间判断函数本身）

```python
from unittest.mock import patch
from datetime import datetime

def test_post_market_detection():
    """验证 _is_post_market() 在 15:10 前后行为正确。"""
    # 模拟 14:50（盘中）
    with patch('quant_tuner.datetime') as mock_dt:
        mock_dt.now.return_value = datetime(2026, 7, 6, 14, 50, 0)
        assert not qt._is_post_market()  # 盘中 → False

    # 模拟 15:10（盘后）
    with patch('quant_tuner.datetime') as mock_dt:
        mock_dt.now.return_value = datetime(2026, 7, 6, 15, 10, 0)
        assert qt._is_post_market()  # 盘后 → True
```

**适用场景**: COOL_OFF_TIME、_is_post_market、_latest_allowed_date、任何依赖 `datetime.now()` 的逻辑

### 3.2 数据构造

**原理**: 不依赖真实数据源，手工构造特定状态的数据来触发目标代码路径。

**构造假日线 DataFrame**（模拟 CSV 读取结果）:

```python
import pandas as pd
from datetime import datetime

# 场景: 验证拆股检测——末笔收盘价异常低（拆后价），历史为拆前价
fake_daily = pd.DataFrame({
    "date":       ["2026-07-01", "2026-07-02", "2026-07-03"],
    "open":       [1.50, 1.55, 1.58],
    "close":      [1.55, 1.58, 0.79],  # ← 末笔只有前一天的一半（模拟 1:2 拆股）
    "high":       [1.52, 1.57, 1.60],
    "low":        [1.48, 1.53, 0.78],
    "volume":     [100000, 120000, 500000],
})

# 验证: CSV 末笔 ÷ 实时价 ≈ 2.0 → 触发清洗
csv_last = float(fake_daily["close"].iloc[-1])  # 0.79
rt_close = 0.76  # 模拟 Sina 实时价（拆后）
ratio = csv_last / rt_close  # 1.04 — 已调整，跳过
# 如果 ratio ≈ 2.0（如 1.58 / 0.76）→ 未调整，触发清洗
```

**构造假 intraday cache**（模拟盘中刷新结果）:

```python
# 场景: 验证回测的盘中数据合并逻辑（_get_daily_with_cache）
# 不需要真的连 Sina API——直接往 CACHE 里塞数据

fake_intraday = {
    "515880": {  # 通信 ETF
        "date": "2026-07-06",
        "open": 0.80, "close": 0.76,
        "high": 0.81, "low": 0.74,
        "volume": 50000000
    },
    "512400": {  # 有色金属
        "date": "2026-07-06",
        "open": 1.50, "close": 1.52,
        "high": 1.53, "low": 1.49,
        "volume": 30000000
    },
}

# 注入 cache 后跑回测:
CACHE["intraday_cache"] = fake_intraday
nav, signals, extra = run_backtest(
    start_date="2026-01-01", end_date="2026-07-06",
    preset="gam-1",
)
# 预期: 回测最后一天使用 intraday 的 close 而非 CSV 的前一日收盘价
```

**构造假拆分事件**（模拟 AKShare 检测结果）:

```python
# 场景: 验证内存清洗逻辑——不想等真实拆股，自己造一个
fake_splits = [
    {"action": "share_split", "ex_date": "2026-07-03", "ratio": 2.0}
]

# 注入到全局缓存（跳过 AKShare 网络调用）:
_SPLIT_EVENTS["515880"] = fake_splits

# 然后用快照对比验证:
# before: daily["close"] 未调整 → 首笔 ≈1.55
# after:  _apply_split_memory_bridge → 首笔 ≈0.775
```

**适用场景**: 拆股检测、数据清洗、边界条件、回测特定数据状态、任何依赖 CSV/cache 的验证

### 3.3 快照对比

**原理**: 改动前后各跑一次，对比结果。适用于重构（不改行为只改实现）后的回归验证。

**对比回测最终净值**:

```python
# 文件: temp_scripts/verify_refactor.py
"""验证重构前后回测结果一致（0.01% 容忍）。"""
import sys
sys.path.insert(0, "scripts")
from quant_backtest import run_backtest

PRESET = "gam-1"
WINDOW = ("2025-06-01", "2025-09-01")

# ── Step 1: 记录重构前结果 ──
# (先 git stash 新代码，跑一次记录结果)
# python temp_scripts/verify_refactor.py --save
# → 写入 temp_scripts/before_result.json

# ── Step 2: 重构后对比 ──
nav, _, _ = run_backtest(start_date=WINDOW[0], end_date=WINDOW[1], preset=PRESET)
after_last = float(nav["nav"].iloc[-1])

# 与保存的基线对比
import json
with open("temp_scripts/before_result.json") as f:
    before = json.load(f)
before_last = before["final_nav"]

diff_pct = abs(before_last - after_last) / before_last
print(f"Before: {before_last:.2f}  After: {after_last:.2f}  Diff: {diff_pct:.4%}")
assert diff_pct < 0.0001, f"NAV drift {diff_pct:.4%} exceeds 0.01% tolerance!"
print("PASS: 重构前后一致")
```

**对比中间计算结果**（不仅是最终净值）:

```python
# 对比更多维度，不只是最终 NAV
nav_before = ...  # 重构前
nav_after  = ...  # 重构后

# 逐日对比净值
assert len(nav_before) == len(nav_after), "行数不一致"
for i in range(len(nav_before)):
    diff = abs(nav_before["nav"].iloc[i] - nav_after["nav"].iloc[i])
    assert diff < 100, f"Day {i}: NAV diff {diff:.0f} 元"  # 1e-4 容忍

# 对比信号序列
signals_before = ...  # [(date, top6), ...]
signals_after  = ...
for (d1, t1), (d2, t2) in zip(signals_before, signals_after):
    assert d1 == d2, f"日期不一致: {d1} vs {d2}"
    assert set(t1) == set(t2), f"{d1}: 持仓不一致 {set(t1)} vs {set(t2)}"
```

### 3.4 退化到基线

**原理**: 新功能应该有一个"关闭"开关。关闭时行为必须与改动前完全一致。这是最可靠的自证方式。

```python
"""验证新功能关闭时退化为旧行为。"""

# 示例 1: 融资利息 rate=0 → 与无融资完全一致
nav_with_rate0, _, _ = run_backtest(
    preset="gam-1", financing_rate=0.0  # 新参数，关闭
)
nav_old, _, _ = run_backtest(
    preset="gam-1",  # 旧代码（假设没有 financing_rate 参数）
)
assert abs(float(nav_with_rate0["nav"].iloc[-1]) -
           float(nav_old["nav"].iloc[-1])) < 1.0  # 差异 < 1 元

# 示例 2: 动态分数带 band_sensitivity=0 → 退化为静态 band
nav_dynamic_off, _, _ = run_backtest(
    preset="gam-1", band=0.03, band_sensitivity=0.0  # 关闭动态
)
nav_static, _, _ = run_backtest(
    preset="gam-1", band=0.03  # 旧: 静态 band
)
assert abs(float(nav_dynamic_off["nav"].iloc[-1]) -
           float(nav_static["nav"].iloc[-1])) < 1.0

# 示例 3: 杠杆=1.0 → 与无杠杆完全一致
nav_lev1, _, _ = run_backtest(preset="gam-1", leverage=1.0)
nav_no_lev, _, _ = run_backtest(preset="gam-1")  # 无杠杆参数
assert abs(float(nav_lev1["nav"].iloc[-1]) -
           float(nav_no_lev["nav"].iloc[-1])) < 1.0
```

**设计原则**: 新参数/新逻辑应该总是可以"关掉"。如果没有关闭开关 → 设计有问题，先加开关再开发。

### 3.5 边界注入

**原理**: 构造极端或异常数据，验证代码不会崩溃且行为合理。重点测"不该发生的事情"。

```python
"""边界注入测试集——验证代码的防御性。"""

# ── 边界 1: 空 intraday cache ──
# 场景: 今天 Sina API 全挂了，intraday_cache 为空
CACHE["intraday_cache"] = {}
result = refresh_data(config)
assert result.get("status") == "confirmed"  # 应正常完成，走 post-market
# 不报 KeyError，不崩

# ── 边界 2: 某支 ETF 完全缺失 CSV ──
# 场景: 新入池 ETF 还没有历史数据
del CACHE["all_daily"]["515880"]  # 模拟缺失
del CACHE["all_weekly"]["515880"]
nav, signals, extra = run_backtest(
    start_date="2026-01-01", end_date="2026-07-06", preset="gam-1"
)
# 预期: 该 ETF 不出现在回测结果中，但不崩溃
for s in signals:
    assert "515880" not in s.get("top6", [])  # 缺失 ETF 不应被选中

# ── 边界 3: CSV 只有 1 行数据 ──
# 场景: 新 ETF 刚拉了一天数据（前复权后可能只有 1 行）
import pandas as pd
single_row = pd.DataFrame({
    "date": ["2026-07-06"], "open": [1.0], "close": [1.0],
    "high": [1.0], "low": [1.0], "volume": [100]
})
CACHE["all_daily"]["NEW_ETF"] = single_row
# 跑回测 → 因子计算应跳过（EMA 需要足够历史），但不崩
nav, _, _ = run_backtest(
    start_date="2026-01-01", end_date="2026-07-06", preset="gam-1"
)
assert len(nav) > 0  # 其他 ETF 正常

# ── 边界 4: 跨周末拆股 gap（周五 ex_date → 周一生效） ──
# 场景: 周五收盘 1.58（拆前价），周末拆分 1:2，周一开盘 0.79（拆后价）
# 验证清洗逻辑能检测到跨非交易日跳变
splits = [{"action": "share_split", "ex_date": "2026-07-03", "ratio": 2.0}]  # 周五
# CSV 末笔 7/3 close=1.58, intraday 7/6 close=0.76
# 7/4-5 是周末，不产生交易日
# → ratio = 1.58/0.76 ≈ 2.08 → 在 [1.7, 2.3] 内 → 触发清洗 ✅

# ── 边界 5: 成交量为 0 ──
# 场景: 停牌 ETF
fake_daily_zero_vol = pd.DataFrame({
    "date": ["2026-07-06"], "open": [1.0], "close": [1.0],
    "high": [1.0], "low": [1.0], "volume": [0]  # 停牌
})
# 回测不应因 volume=0 而除零崩溃
```

### 3.6 参数扫描

**原理**: 取几个关键参数值（零/默认/极端），验证行为单调性和方向正确。不必穷举，3-4 个点就能看出方向对不对。

```python
"""参数扫描验证——用几个关键取值快速判断逻辑方向。"""

# ── 验证 band 的倒 U 型 ──
# 测得: band=0→AR=90.8%, band=0.03→AR=102.6%, band=0.08→AR=81.6%
# 说明: 倒 U 型成立，band=0.03 附近是最优区间
results = {}
for band in [0, 0.03, 0.08, 0.20]:
    nav, _, _ = run_backtest(preset="gam-1", band=band)
    results[band] = float(nav["nav"].iloc[-1])
    print(f"band={band}: final NAV={results[band]:.0f}")

# 断言: band=0.03 应优于 band=0（有 band > 无 band）
assert results[0.03] > results[0], "band 应该提升收益"
# 断言: band=0.20 应劣于 band=0.03（过宽 → 换手不足）
assert results[0.03] > results[0.20], "band 过宽应降低收益"

# ── 验证融资利率单调性 ──
for rate in [0, 0.03, 0.06, 0.10]:
    nav, _, _ = run_backtest(
        preset="gam-1", financing_rate=rate
    )
    print(f"rate={rate:.0%}: final NAV={float(nav['nav'].iloc[-1]):.0f}")

# 断言: rate 越高收益越低（单调递减）
# rate=0.06 > rate=0 → 有成本比没成本差

# ── 验证杠杆的双向放大效应 ──
# 杠杆不仅放大收益也放大亏损——MDD 应随 leverage 单调递增
for leverage in [0.5, 1.0, 1.5, 2.0]:
    nav, _, _ = run_backtest(
        preset="gam-1", leverage=leverage
    )
    mdd = _compute_mdd(nav)  # 假设有 MDD 计算函数
    print(f"leverage={leverage}: MDD={mdd:.1%}")
# 断言: leverage=2.0 的 MDD > leverage=1.0 的 MDD

# ── 扫描技巧: 缩小窗口加速 ──
# 6Y 全量太慢 → 先缩小到 1Y 验证方向，确认后再跑全量
for band in [0, 0.03, 0.08]:
    nav, _, _ = run_backtest(
        preset="gam-1", band=band,
        start_date="2025-01-01", end_date="2026-01-01",  # 1Y 代替 6Y
    )
    print(f"band={band}: 1Y NAV={float(nav['nav'].iloc[-1]):.0f}")
```

### 3.7 日志断言

**原理**: 不只看"没报错"，要 grep 特定关键字确认走了预期代码路径。日志是代码路径的指纹。

```bash
# ── 验证走 post-market 而非 intraday ──
python scripts/preclose_push.py --output-md 2>&1 | grep -E "(Post-market|confirmed)"
# 预期输出含 "Post-market" 或 "confirmed"
# 如果输出是 "intraday" → 时间不对，检查 COOL_OFF_TIME

# ── 验证 CSV 写入成功 ──
python scripts/preclose_push.py --output-md 2>&1 | grep -E "Wrote.*daily\.csv|写入"
# 或直接检查 CSV 文件本身:
grep "$(date +%Y-%m-%d)" data/quant/512400_daily.csv
# 预期: 有一行以今天日期开头

# ── 验证拆股清洗触发 ──
grep "Bridge.*split bridge" tuner.log
# 预期: 有输出 → 清洗触发（CSV 未调整）
# 无输出 → 清洗跳过（CSV 已调整 或 无拆股事件）

# ── 验证清洗跳过（自愈生效） ──
# 在 refresh_data 输出中检查:
python -c "
import subprocess, sys
result = subprocess.run(
    [sys.executable, 'scripts/preclose_push.py', '--output-md'],
    capture_output=True, text=True
)
output = result.stdout + result.stderr
if 'split bridge' in output.lower():
    print('FAIL: 清洗被触发（CSV 可能未调整）')
elif 'already adjusted' in output.lower() or 'skip' in output.lower():
    print('PASS: 清洗自愈跳过')
else:
    print('INFO: 无拆股事件或无相关日志')
"

# ── 验证回测使用了正确的数据源 ──
# 回测日志应包含 "loaded X ETFs from CSV" 或 "merged intraday cache"
grep -E "(loaded.*ETFs|merged.*cache|intraday_cache)" tuner.log
```

### 3.8 用户协助验证

**使用条件**: AI 确实无法执行的验证。必须给出**精确的检查步骤**，不要"请验证一下"。

```markdown
需用户协助验证:
1. 浏览器打开 http://localhost:5179 → F12 → Console → 检查无红色报错
2. 左侧栏"赌徒"标题应显示 "▶ 赌徒 (max AR, MDD≥-40)" → 点击展开 → 箭头变 "▼"
3. 刷新数据按钮 → 进度条应均匀推进，不在 90% 卡住
```

---

## 四、验证反模式（禁止）

| 反模式 | 为什么不行 | 应该怎么做 |
|--------|-----------|-----------|
| "日志没报错，应该没问题" | 很多 bug 不产生异常（BUG-038 杠杆从未生效，无报错） | 检查下游产物：CSV、回测结果、推送内容 |
| "status=ok 就是通过了" | status 只说明 API 调通，不说明逻辑正确 | 检查实际数据变化 |
| "环境因素，真环境就好了" | 验证不通过就是不通过 | 换不依赖环境的方法验证，或标记"用户协助" |
| "代码看起来正确" | lookahead bias、set 顺序不确定性肉眼看不出来 | 必须执行 |
| "改了 1 行，不用测" | BUG-025（lookahead bias）只改了一个参数 `direction="backward"` | 改 1 行也必须验证 |
| "之前跑通过" | 数据变了、代码上下文变了 | 每次改动后重新验证 |
| "写了个测试脚本，虽然没跑" | 没执行的测试等于没写 | 必须执行并看到 PASS |
| "pytest 全绿"但没覆盖新增代码 | 旧测试不覆盖新逻辑 | 新逻辑必须有对应测试 |

---

## 五、验证脚本存放约定

| 目录 | 用途 | 生命周期 |
|------|------|---------|
| `tests/` | 长期回归测试，提交到 Git | 永久保留 |
| `_working/` 或 `temp_scripts/` | 单次验证脚本，调试用 | 任务结束时清理或提升 |

**提升规则**: `_working/` 中的验证脚本如果满足以下条件 → 移到 `tests/`：
1. 验证的逻辑是核心路径（回测/因子/清洗/数据管线）
2. 不依赖特定日期或特定数据状态（或通过 mock 解耦）
3. 可在 CI 中运行（不需要 Tuner 进程、不需要真实网络）

---

## 六、与 AGENTS.md 验证门禁的关系

本文档是**武器目录**。AGENTS.md 中定义的**验证门禁协议**规定"何时必须验证"和"验证输出格式"。

武器选择流程：
```
改动类型 → 查场景映射表(§二) → 选择合适的武器(§三) → 执行验证 → 按门禁协议输出报告
```
