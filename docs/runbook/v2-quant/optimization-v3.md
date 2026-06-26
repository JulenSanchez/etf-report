# 参数优化规范 v3（帕累托前沿）

> **触发词**: "优化 <preset>"。AI 自动执行三轮无 prune 收敛，产出 (risk, target) 前沿曲线。
> **状态**: 草案。当前仍按 v2 (`optimization.md`) 执行。

## 一、设计

```
Round 1 泼墨    Sobol 70   无约束 无prune    全空间散点
Round 2 扩散    TPE 80     target最大化      前沿外推
Round 3 收敛    TPE 50     界收缩            前沿光滑化

不 prune —— 每个 trial 都是前沿上的一个样本
```

```
AR ^
   |                        ··  Round 3
   |                   ····    
   |              ·····       ··  Round 2
   |          ···· 
   |      ····                ··  Round 1 散点
   |  ····
   |··
   +-----------------------------> MDD
```

## 二、目标与风险

### 三周期等权（强制约定）

所有优化跑 6Y 全窗口。1Y/3Y/6Y 从同一条 NAV 曲线截取，不独立跑多段回测。

```
target = (1Y_AR + 3Y_AR + 6Y_AR) / 3
```

### 统一表达

```
preset = { target, risk }
         target ∈ {annual_return, sortino, calmar}   ← 均为三周期等权
         risk   ∈ {mdd, bear, null}
```

| preset | target | risk | 输出 |
|--------|--------|------|------|
| gam | composite AR | mdd | (MDD, composite AR) 帕累托前沿 |
| zen | composite Sortino | — | 单点最优 |
| act | composite Calmar | bear | (bear, composite Calmar) 前沿 |

三轮框架完全一致。差异仅在 target 和 risk。有 risk 时产出前沿，无 risk 时产出单点。

## 三、全参数单阶段搜索

```
搜: w1, w3, f7_t, f7_k, f7_window, f3_vol_window,
    f1_sensitivity, f3_sensitivity, f1_ema_period,
    ma_bull_pos, ma_bear_pos, max_holdings,
    ma_trend_period, concentration, c_sensitivity, score_band

固定: conf_type=ma_trend, ma_direction_confirm=True,
      rebalance_freq=daily, disc_step=基线, w7=100-w1-w3
```

16 个参数，单阶段。不拆层。

## 四、Round 细节

### 核心原则：不 prune

```
传统:   约束不满足 → raise TrialPruned → trial 作废
v3:     永远不 prune。每个 trial 记录 (risk_value, target_value)
        不管 risk 好不好，都作为前沿的一个样本保留
```

### Round 1 — 泼墨

| 项 | 值 |
|----|-----|
| 算法 | Sobol 准随机 |
| trials | 70 |
| prune | **永不** |
| 约束 | 仅 bull > bear（仓位基本合理性）|
| 参数界 | PARAM_BOUNDS 全范围 |
| 产出 | 第一条粗糙前沿 + 全空间覆盖 |

**门禁**：存活 ≥ 50 → 继续。否则参数界放宽 50% 重跑。

### Round 2 — 扩散

| 项 | 值 |
|----|-----|
| 算法 | TPE, multi-start from Round 1 前沿上均匀采样的 10 个点 |
| trials | 80 |
| prune | **永不** |
| objective | `target` — TPE 只追目标最大化，不管 risk |
| 参数界 | Round 1 存活区的 1.5× |
| 产出 | 前沿外推：新 trial 在已有散点的基础上向高 target 方向延伸 |

> 为什么只追 target 不约束 risk？因为不 prune。TPE 自然会发现高 target 往往高 risk（正相关）或低 risk（负相关）。tradeoff 曲线从数据中浮现，不需要人工预设。

**门禁**：前沿上 ≥ 20 个点 → 继续。

### Round 3 — 收敛

| 项 | 值 |
|----|-----|
| 算法 | TPE, warm-start from Round 2 前沿 |
| trials | 50 |
| prune | **永不** |
| objective | `target` |
| 参数界 | Round 2 前沿 top-30% trial 的参数范围 × 1.2 |
| 产出 | 光滑密集的帕累托前沿 |

**门禁**：前沿改善 < 1% → 收敛完成。

## 五、前沿输出与应用

### 输出格式

```
每条 trial 记录: {params, risk_value, target_value}
前沿: 按 risk 排序后，对每个 risk 取 max(target_value) 的 trial 集合
```

### 用户使用

```
1. 看 (risk, target) 曲线 → 找到"膝盖"（risk 放松时 target 不再显著提升的点）
2. 从曲线挑参数 → 写入 preset
3. 新增中间约束值不需重跑 → 从已有前沿插值
```

## 六、任意起点

```
场景 A: 有旧优化参数 → Round 1 半 Sobol + 半旧邻域
场景 B: 参数空间变 → 100% Sobol
场景 C: 只需补充前沿 → 从现有前沿 warm-start Round 2
```

## 七、v2 → v3 关键差异

| | v2 | v3 |
|------|-----|-----|
| prune | 约束不满足→丢弃 | 永不丢弃 |
| 输出 | 单个最优点 | 完整风险-收益曲线 |
| 约束 | 预设固定值 | 事后从曲线上取值 |
| 分层 | 信号→执行 | 单阶段全参数 |
| 三派 | 各自写法 | 统一 target+risk 模板 |
| trial 利用 | ~50% 被 prune | 100% 保留 |
