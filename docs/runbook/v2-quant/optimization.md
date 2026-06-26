# 参数优化规范（帕累托前沿）

> **触发词**: "优化 <preset>"。AI 自动执行三轮收敛，产出 (risk, target) 前沿。

## 一、设计

```
输入:  参数空间 + target指标 + risk指标 + (可选的 warm-start trial 列表)
输出:  (risk, target) 帕累托前沿 → 一组 {params, risk, target}

Round 1 泼墨    Sobol 80    无约束         覆盖全空间
Round 2 扩散    TPE 80      warm-start     前沿外推
Round 3 收敛    TPE 50      warm-start     前沿光滑化

不 prune —— 每 trial 都是前沿样本
```

## 二、引擎接口

引擎是纯方法。不知道任何 preset 名称或参数值。

```
optimize(
    param_space:   Dict[str, Distribution]    # 搜哪些参数、各自范围
    target:        "annual_return" | "sortino" | "calmar"
    risk:          "mdd" | "bear" | null
    warm_start:    List[Trial] | null          # 可选：已有 trial 数据
    fixed_params:  Dict[str, value]            # 固定参数
) → List[{params, risk_value, target_value}]
```

**target 均为三周期等权**。6Y 全窗口，1Y/3Y/6Y 从同一条 NAV 截取。

```
target_value = (1Y_AR + 3Y_AR + 6Y_AR) / 3
```

## 三、warm-start 逻辑

引擎不关心 trial 从哪来——可能是预设库、上次优化结果、或人工构造。

```
if warm_start 非空:
    # 验证每个 trial 的 params 都在 param_space 内
    valid = warm_start.filter(params ⊆ param_space)
    if len(valid) >= 2:
        R1 采样: 40% Sobol + 30% valid邻域 + 30% 两两交叉变异
    elif len(valid) == 1:
        R1 采样: 50% Sobol + 50% valid邻域
    else:
        R1 采样: 100% Sobol
else:
    R1 采样: 100% Sobol
```

**交叉变异**：随机取两个 valid trial，各一半参数混合。目的是产生"gam-1 信号 × gam-2 执行"这种意外组合——但引擎不知道也不关心这些名字。

**如果 warm_start 数据不可靠**（如 BUG-038 修复后的情况）：不传 warm_start，引擎纯 Sobol 起步，不依赖任何旧数据。

## 四、Round 细节

### Round 1 — 泼墨

| 项 | 值 |
|----|-----|
| 算法 | Sobol |
| trials | 80 |
| 约束 | 仅 bull > bear |
| 参数界 | param_space 全范围 |

**门禁**：存活 ≥ 60。目标 risk 区间前沿点 < 5 → 追加 30 trial。

### Round 2 — 扩散

| 项 | 值 |
|----|-----|
| 算法 | TPE |
| trials | 80 |
| warm-start | Round 1 全部 trial |
| objective | target |
| 参数界 | Round 1 存活区 × 1.5 |

**门禁**：前沿改善 > 2% → Round 3。否则收敛完成。

### Round 3 — 收敛

| 项 | 值 |
|----|-----|
| 算法 | TPE |
| trials | 50 |
| warm-start | Round 2 全部 |
| objective | target |
| 参数界 | Round 2 top-30% × 1.2 |

**门禁**：改善 < 1% → 完成。

## 五、预设库

预设库是使用引擎的**调用方**，不在引擎内部。由回测系统的 `quant_universe.yaml` 和 `quant_contract.py` 管理。

```
预设库 = {
    "gam-1": {params, ...},
    "gam-2": {params, ...},
    ...
}
```

调用方负责：
1. 从预设库提取 trial 列表 → 作为 warm_start 传入引擎
2. 从引擎输出的前沿曲线中选择参数 → 写回预设库
3. 标记不可靠的预设（如 BUG-038 后）→ 不传入 warm_start

引擎不反向依赖预设库。

## 六、设计原则

- **引擎无预设依赖**：不知道 gam-1、gam-2 等名字，只接收 param_space + target + risk
- **warm-start 外部化**：已有 trial 数据由调用方传入，不可靠则不传
- **不 prune**：每个 trial 都是前沿样本
- **事后决策**：约束值从前沿曲线上选取，优化时不预设
