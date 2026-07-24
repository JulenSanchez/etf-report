---
description: 暴露 bug 而非隐藏——反模式/正模式对照 + 自检清单
alwaysApply: true
priority: P1
---

# 暴露 bug 而非隐藏 bug

## 核心原则

> 遇到异常/警告/错误时，**必须优先寻找并修复根因**。禁止用抑制、吞掉、包装的方式让症状消失。

AI 是"临时施工队"，不是"项目主人"。施工队不应该把问题粉刷进墙里让下一个人踩坑。bug 暴露出来，至少还能被发现和修复；bug 被隐藏，会在更深的层面、更晚的时间爆发，代价指数级放大。

## 反模式（禁止）

### 1. 抑制症状

```python
# ❌ 抑制警告后假装没事
import warnings
warnings.filterwarnings('ignore', message='range not divisible by step')
# optuna 采样空间有偏差，TPE 收敛变慢，但日志干净
```

### 2. try/except 吞异常

```python
# ❌ 异常被吞，调用方不知道失败原因
try:
    result = run_backtest(params)
except:
    result = None
if result is None:
    pass  # 走 fallback，但不知道为什么失败
```

### 3. 返回 0/None/[] 掩盖失败

```python
# ❌ 调用方无法区分"真的 0"和"失败返回 0"
def fetch_etf(code, date):
    try:
        return api.get(code, date)
    except:
        return 0
```

### 4. 包装语义不一致

```python
# ❌ 前端承诺"覆盖式更新"，后端实际"增量"，用 toast 文案抹平差异
# 用户看到"日线数据已是最新"以为正常，实际是语义没对齐
```

### 5. 缩小检测范围让测试通过

```python
# ❌ split_status 只看最后 2 行，拆股跳变被新数据盖住 → "测试通过"
last = close[-1]; prev = close[-2]
if abs(last - prev) / prev > 0.30:
    flag_split()
```

### 6. 修复时引入额外副作用

```python
# ❌ 修 intraday 残留 bug 时顺手清理整个 cache
if is_post_market and cache.get("intraday"):
    cache["intraday"] = {}  # 用户指出"过度清理"后才回滚
```

### 7. 推给用户复现

```
# ❌ "建议下次复现时截图对比" / "刷新浏览器试试，不行再找我"
# AI 应该主动加可观测性、构造触发条件，而不是把排查责任推给用户
```

## 正模式（要求）

### 1. 修复根因，让症状自然消失

```python
# ✅ 找出产生警告的代码，修根因
import math
lo = math.floor(lo / step) * step
hi = math.ceil(hi / step) * step
# bounds 对齐 step，警告自然消失，采样空间正确
```

### 2. 暴露状态：结构化错误 + UI 显示

```python
# ✅ 操作失败时返回结构化错误，UI 用 toast/banner 显示
def fetch_etf(code, date):
    try:
        return {"ok": True, "data": api.get(code, date)}
    except ApiError as e:
        return {"ok": False, "error": str(e), "code": code, "date": date}
```

```js
// 前端不把 error 当 success 处理
if (!data.ok) {
  dmToast('失败: ' + data.error, 'error');
  return;
}
```

### 3. 扩大检测范围找 bug

```python
# ✅ 扫描最近 N 行，让跳变能被发现
for i in range(len(close)-1, max(len(close)-10, 1), -1):
    if abs(close[i] - close[i-1]) / close[i-1] > 0.30:
        flag_split(); break
```

### 4. 主动构造 bug（假数据注入）

```python
# ✅ 不等用户复现，主动构造触发条件
# 1. 读 515880_daily.csv
# 2. 将 ex_date 之前所有 close × 2（模拟拆前价）
# 3. 删除 ex_date 之后的数据
# 4. 验证系统能检测到跳变 → 标记 → 修复 → 验证
```

### 5. 保留可观测性

```python
# ✅ 关键决策点保留 info 级 log，排查时能回溯
import logging
log = logging.getLogger(__name__)
log.info(f"Split repair: code={code} ratio={ratio} mask={mask.sum()} "
         f"before={before_close:.4f} after={after_close:.4f}")
```

### 6. 最小修复，不顺手重构

修 bug 时只改必须改的。如果发现旁边的代码也该改，登记一个新的 REQ/BUG，不要在当前修复里夹带。

## 自检清单

写代码前问自己：
- [ ] 这个 `try/except` 是为了处理已知异常，还是为了"防止崩溃"？
- [ ] 这个 `warnings.filterwarnings` 是兜底，还是掩盖根因？
- [ ] 返回值能否区分"成功"和"失败"？还是用同一个值掩盖了失败？
- [ ] 修复 bug 时有没有顺手改旁边的代码？是否应该拆成独立 PR/REQ？
- [ ] 用户看到这个错误信息能知道原因吗？还是只是"操作失败"？
- [ ] 我是在主动构造 bug 验证修复，还是在等用户复现？
