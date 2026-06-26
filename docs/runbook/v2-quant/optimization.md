# 参数优化全流程约定

> **触发词**: 用户说"优化 <preset>"。AI 自动：自检数据 → 推导搜索空间 → 执行 → 出 analysis.json → 写报告。详见本文。

AI 与用户的协作契约。优化启动前双方各司其职，减少反复沟通。

## 一、用户如何发起

### 最小提示词

```
优化 <preset>
```

例：`优化 gam-2`、`优化 zen-1`

AI 应自动从 `PRESET_OPT_PROFILES` 读取 metric 和约束，从 preset 当前值推导搜索范围，无需用户指定。

### 完整提示词（覆盖默认值）

```
优化 <preset>，目标 <metric>，约束 <constraint>，<n> trials，<周期>
```

例：`优化 gam-2，目标 total_return，约束 mdd,-15，100 trials，6Y`

### 多 preset 批量

```
优化 gam-2 zen-1 act-1，70 trials，6Y
```

AI 自动串行执行，每完成一个立即写报告。

## 二、AI 执行前自检（AI 必须逐条确认）

| # | 检查项 | 动作 |
|---|--------|------|
| 1 | 数据是否新鲜？ | `python scripts/quant_data_fetcher.py` 确认 CSV 最新日期为最近交易日 |
| 2 | 盘中还是盘后？ | 盘中（9:30-15:10）→ 警告用户"回测会包含不完整日内数据" |
| 3 | Config 是否有未提交的改动？ | `git diff config/quant_universe.yaml` 检查，有改动 → 询问是否先提交 |
| 4 | 搜索范围覆盖基线值？ | 手动验证 `--params` 中每个参数的 min/max 包含基线值 |
| 5 | 权重参数 sum=100？ | 搜索的 w1/w3 范围 + 固定 w7 必须 sum=100，否则 residual 会调整 |
| 6 | disc_step 精度？ | 如果预设 disc_step 不是整数百分点，确认滑块 max 足够 |

## 三、AI 执行规范

### 默认参数

- `--strategy bayesian`
- `--n-trials 70`
- `--periods 1Y,3Y,6Y`（三周期等权 composite = mean(1Y_rel, 3Y_rel, 6Y_rel)）
- `--universe '*'`
- `--auto-bounds`
- 1Y/3Y 数据从 6Y 回测 NAV 截取，不独立跑（确保"策略跑了 5 年后最近 1 年到底表现如何"）
- metric 和约束 → 脚本默认从 `PRESET_OPT_PROFILES` 读取；用户显式传 `--metric` / `--constraint` 时覆盖

### 信号层与执行层分离（强制约定）

参数优化必须分两层、按顺序执行，禁止联合优化：

| 层 | 管什么 | 参数 | 搜索轮次 |
|----|-------|------|:--:|
| **信号层** | 选股——什么值得买 | w1, w3, w7, f7_t, f7_k, f7_window, f1_sensitivity, f3_sensitivity, f3_vol_window, f1_ema_period | **第一轮** |
| **执行层** | 配比——买多少、怎么分 | max_holdings, ma_bear_pos, ma_bull_pos, disc_step, concentration, c_sensitivity, score_band, ma_trend_period | **第二轮** |

**执行规则**：

1. **第一轮（信号层）**：锁死执行层参数为基线值，只搜索信号层参数。产出最优信号参数。
2. **第二轮（执行层）**：锁死信号层参数为第一轮最优值，只搜索执行层参数。产出最终参数组合。
3. 使用 `--two-stage` 时两轮自动串联：信号层通过质量检查（≥5 trials + composite > 0.95）后自动继续，否则停止报警。

**分离理由**：

- 信号质量（选什么）和仓位管理（买多少）是正交问题。联合优化会制造补偿效应——劣质信号被激进仓位救回来，但实盘中不稳定。
- 分层后每轮只有 3-5 个参数，TPE 收敛更快、过拟合风险更低。
- 分开后可以直接回答"这个 preset 好是因为选股准还是风控好"。

### 搜索参数规范

#### 信号层参数（第一轮）

70 trials 6Y，锁死执行层为基线值。

| 参数 | 搜索范围 | 说明 |
|------|---------|------|
| w1 | [bl-10, bl+10] 步长 1 | F1 趋势偏离权重。越高越依赖趋势信号 |
| w3 | [bl-10, bl+10] 步长 1 | F3 量比权重。越高越看成交量 |
| f7_t | [3, 15]（若 bl>15 则 [bl-5, bl+5]） | F7 幂次。越高对小偏离越中性，过滤噪音 |
| f7_k | [1.5, 5.5] | F7 标准差倍数。幂函数→切线切换点，越大中性区越宽 |
| f3_vol_window | [bl-15, bl+15] 步长 1 | F3 量比计算窗口（天） |
| f7_window | [bl-10, bl+10] 步长 1 | F7 对数收益窗口（天） |

#### 执行层参数（第二轮）

70 trials 6Y，锁死信号层为第一轮最优值。

| 参数 | 搜索范围 | 说明 |
|------|---------|------|
| ma_bear_pos | 赌徒 [0.3, 1.0] / 禅修 [0.15, 0.5] / 精算 [0.15, 0.30] | 熊市仓位 |
| max_holdings | [1, 8] 步长 1 | 最大持仓数。越小越集中，1=单吊 |
| disc_step | [0.03, 0.15] 步长 **0.01（整数百分比）** | 仓位离散化步长 |
| ma_trend_period | [bl-5, bl+15] 步长 1 | MA 趋势计算周期（周） |
| concentration | [bl*0.5, bl*2.0] | 仓位集中度 C |
| c_sensitivity | [bl*0.5, bl*2.0] | C 动态灵敏度 |
| score_band | [0.5, 8.0] 步长 **0.1** | 分数带（%）。越小越挑剔 |

#### 精细优化参数（可选扩展）

若分层优化后仍需进一步调优，以下参数可按需加入对应层：

| 参数 | 所属层 | 搜索范围 | 说明 |
|------|:--:|------|------|
| f1_sensitivity | 信号层 | [bl*0.5, bl*2.0] | F1 sigmoid 陡峭度 |
| f3_sensitivity | 信号层 | [bl*0.5, bl*2.0] | F3 log-sigmoid 陡峭度 |
| f1_ema_period | 信号层 | [bl-2, bl+4] 步长 1 | F1 EMA 均线周期（周） |
| ma_bull_pos | 执行层 | cash: [0.8, 1.0]；synthetic_leverage: 见 `docs/design/margin-account-model.md` | 牛市目标暴露 |

> **单位转换说明**：以下参数的搜索范围为 Tuner/CLI UI 值，与 `config/quant_universe.yaml` 中的存储值存在换算关系：
>
> | 参数 | UI (Tuner/CLI) | Config YAML | 换算 |
> |------|---------------|-------------|------|
> | `concentration` | 0-30 (范围) | 0-3.0 | UI = Config × 10 |
> | `c_sensitivity` | 0-200 (范围) | 0-20.0 | UI = Config × 10 |
> | `score_band` | 0-20% (范围) | 0-0.2 | UI% = Config × 100 |
>
> CLI `--params "concentration=10:20:0.1"` 使用 Tuner/UI 值，不是 Config 值。

#### 三派初始 Preset（优化起点）

优化从 `quant_contract.py::INITIAL_PRESETS` 读取初始值——信号层通用中性起点，执行层按 gam/zen/act 前缀取对应值。具体数值见代码常量，不在此重复。

#### 锁定参数

以下参数固定基线值，不参与搜索：

| 参数 | 固定值 | 说明 | 锁定理由 |
|------|--------|------|---------|
| w7 | 100-w1-w3 | F7 权重 | residual 自动计算，保持 sum=100% |
| bias | 0 | 扇区偏好加分 | 已证实对策略无益 |
| conf_type | ma_trend | 信心函数类型 | 不搜索 |
| account_mode | synthetic_leverage | 账户模式 | 默认杠杆，不搜索。Tuner 前端可选现金/杠杆 |
| ma_bull_pos | cash 模式 1.0 | 牛市目标暴露 | 杠杆模式下可搜索（执行层）。范围由 `max_gross_exposure`（默认 2.0）决定 |
| ma_direction_confirm | True | 方向确认 | 防止假突破 |
| full_zone | 65 | 旧信心函数满配阈值 | conf_type=ma_trend 时不生效 |
| dead_zone | 基线值 | 死区——分数在此区间不调仓 | **conf_type=ma_trend 下不生效**，即使搜索也无效果。保留在 preset 中仅兼容旧代码 |
| rebalance_freq | daily | 调仓频率 | 锁死 |
| f1_active_days | 1 | F1 活跃天数 | 锁死 |
| f1_ema_period | 基线值 | F1 EMA 均线周期（周） | 尚未测试灵敏度，默认不搜索 |

### 权重处理

w1、w3、w7 中：w1 和 w3 搜索，w7 固定基线值。`auto_bounds` + `--params` 正确写法：
```
w1=48:65:1 w3=18:30:1 ... w7=20 bias=0 conf_type=ma_trend ...
```
固定值参数用单值（如 `w7=20`），搜索参数用范围（如 `w1=48:65:1`）。

### 并行限制

| 场景 | 是否可并行 | 原因 |
|------|:--:|------|
| **同 preset 信号层 → 执行层** | ❌ 串行 | 执行层依赖信号层最优值 |
| **不同 preset 之间** | ❌ 串行 | 共享 `quant_data_cache` + CSV 缓存目录，多进程同时读写会冲突 |
| **同 preset 内 trials** | ❌ 串行 | GIL 限制，TPE 本身也不支持 trial 级并行 |

所有优化必须串行执行。如需并行，需先做缓存隔离改造（不同 preset 使用独立缓存目录）。

## 四、AI 完成后交付

### 必须交付物

1. `research/params/<preset>-<date>/analysis.json`（优化器自动生成）
2. `research/params/<preset>-<date>/report.md`（AI 基于 analysis.json 写叙事报告）
3. `analysis.json` 包含 6 个结构化字段，报告每节必须消费对应字段（见下方门禁表）

### 质量门禁（硬性，缺任一节视为未完成）

#### 数据源映射

每节必须使用指定的 analysis.json 字段，不得凭空编造：

| 节 | 数据源（analysis.json） | 门禁 |
|----|----------------------|------|
| §2 搜索的故事 | `convergence` | 至少引用 3 个具体 trial 编号 + 参数值 + TR 数值 |
| §3 参数重要性 | `top_bottom_divergence` | Top 10 vs Bottom 10 均值对比表，每行有具体数值 |
| §4 市场阶段归因 | `phase_performance` | 分阶段表，附解读（不是只列数字） |
| §5 行为诊断 | `behavioral_baseline` | Best / Median / Worst trial 的行为差异对比 |
| §6 ETF 四象限 | `etf_quadrants` | 四类全列，核心/需排查必须有 P&L + 选中率 + 胜率 + 赔率 |
| §7 极端场景 | `top_trials[0].holdings_distribution` | 极端集中统计（频率、时长、标的）、MDD 期间持仓明细。**杠杆策略还必须提供 `extreme_analyzer.py` 输出**（整体胜率 + per-ETF 分类 + 裁决，见 preset-change.md §极端集中分析） |
| §8 局限与后续 | `bootstrap` | ≥2 个具体的后续研究方向 + **Top 3 的 bootstrap 稳健性数据（median_final / P5 / 毁灭概率）** |

#### 参数重要性门禁细则

除 Top-Bottom 对比表外，必须包含 **≥1 项控制变量验证**：选一个敏感参数，固定其余，单变量扫参（≥4 个值），产出一张对比表。如 MH=3/4/5/6/7 的 TR/MDD/Sharpe 表。

#### 归因拆解（分层优化时）

| 指标 | 来源 |
|------|------|
| 信号层 Δ | 第一轮 best trial TR − 基线 TR（执行层锁定基线值） |
| 执行层 Δ | 第二轮 best trial TR − 第一轮 best trial TR |
| 交互增益 | 总 Δ − 信号层 Δ − 执行层 Δ（信号+执行联合生效 vs 单独生效的差值） |

#### 完成自检清单

报告写完后，AI 必须逐条输出确认：

```
[ ] §2 引用了 ≥3 个具体 trial 编号
[ ] §3 有 Top 10 vs Bottom 10 参数均值表
[ ] §3 有 ≥1 项控制变量验证（≥4 个值的扫参表）
[ ] §4 有分阶段表 + 解读
[ ] §5 有 Best/Median/Worst 行为对比
[ ] §6 四类 ETF 全列，核心/需排查有定量四维数据
[ ] §7 有极端集中统计 + MDD 持仓明细（杠杆策略还必须附 `extreme_analyzer.py` 输出，见 preset-change.md §极端集中分析）
[ ] §8 有 ≥2 个具体后续方向 + Top 3 bootstrap 数据
[ ] 有明确的"是否建议采纳"判断
[ ] analysis.json 的 `bootstrap` 字段存在且包含 ≥1 个 trial
```

若不通过，AI 不报告完成。

### 方法论边界

以下为固定结论，不因对话而改变：

- **标准流程 = 两轮（信号→执行）**，不做多轮迭代
- **多样本鲁棒性检查**是可选研究工具，不进标准流程
- **三派各自维护自己的 preset** 作为优化起点，不做通用中性模板
- **分层优化归因拆解**：信号层 Δ（执行锁基线）、执行层 Δ（信号锁最优）

### 子 Agent 报告生成

**前置条件**：optimizer 已完成（`.optimizer_done` 或 log.txt 末尾有 "DONE"）。

**执行**：委派子 agent，agent 先跑 analyzer 生成 analysis.json，再读 §八 硬模板写 report.md + 自检清单。父对话只做 promote/reject 决策。

**Agent 输入**：study name、输出目录、§八 硬模板。
**Agent 输出**：analysis.json + report.md + 自检清单。

**杠杆策略额外步骤**：若 preset 的 mbull > 1.0，agent 必须在 report §7 中包含 `extreme_analyzer.py` 的输出。运行 `python scripts/extreme_analyzer.py --preset <name>`，将整体胜率、per-ETF 分类、裁决写入 §7。promotion 决策需综合考虑此分析结果。

**常见错误**：optimizer 的自带 report 不包含 analysis.json——agent 必须自己跑 analyzer，不可跳过。

### 不自动做的事

- **不自动写入 config**（等用户确认）
- **不自动提交 git**（等用户确认）
- **不自动删除旧 preset**
- **不自动跳过极端集中分析**（杠杆策略，见 `docs/runbook/v2-quant/preset-change.md §极端集中分析`）

## 五、故障排查

| 症状 | 原因 | 处理 |
|------|------|------|
| 优化器 TR 远低于基线 | 权重 sum≠100，或搜索范围不覆盖基线 | 检查 resolved 权重 sum，检查 auto_bounds 范围 |
| Tuner 前端 TR 与 CLI 不一致 | 1) Tuner 缓存旧 config 2) disc_step slider 截断 3) 日内数据 | 重启 Tuner，检查 slider max，等收盘 |
| `--constraint` 不生效 | argparse 格式错误 | 确认 `--constraint mdd,-20` 无空格、无 % 号 |
| 优化器 OOM | 54 支全池 + preload 数据 ~2GB | 减少 trial 数或重启进程 |
| resolve_weights 改变所有权重 | 固定值参数被当作 weight 类型 | 确认 w7 用 `w7=20` 格式（非 weight type）|
| `DuplicatedStudyError` 重复 study | 旧 run 的 optuna.db 未被删除（Windows 文件锁） | 优化器已自动处理：目录存在时自动追加 `-v2`/`-v3`，无需手动改名 |

## 六、环境约定

| 事项 | 约定 |
|------|------|
| 数据刷新 | 优化前必须拉最新 CSV（`quant_data_fetcher.py`） |
| 盘中优化 | 警告但不阻止——用户可能想对比日内 vs 收盘结果 |
| git 状态 | dirty working tree → 必须先提交或 stash，否则不跑 |
| Tuner 端口 | 优化器不绑端口，不受 `_ensure_tuner` 影响 |
| 输出目录 | `research/params/<preset>-YYYYMMDD/`，自动创建 |

## 七、分析哲学

### 发现驱动，而非验证驱动

报告的价值在于**从数据中发现用户没说的洞察**。如果用户已经说了"金融科技被盘活"，你只需要验证——那报告就只是整理。好的报告应该：

- 从 TPE 收敛轨迹、参数分布、回测行为中**主动挖掘**值得讲的发现
- 用户给的观察是**起点的线索**，不是终点的结论
- 每节都要问自己：这节有没有讲出用户自己看不出来的东西？

### 分析师视角

把优化结果当成一次**策略体检**。你看到的不仅是"TR 涨了 300pp"——你要解释**为什么涨了、靠什么涨的、涨在哪个阶段、有什么风险**。

## 八、报告结构（硬模板）

以下为报告必须遵守的结构。Agent 需逐节按模板生成，不自行增减节数。

### §1 优化概览

必须包含: 方法、trial 数、搜索空间、基线 vs Best 对比表（TR/MDD/Sharpe/Annual）、采纳参数表（按层分列，含基线→最优的变化方向）

### §2 搜索的故事

必须包含: **≥3 个具体 trial 编号 + 每个 trial 的关键参数值 + TR 数值**，形成"参数如何逐步逼近最优"的叙事。TPE 收敛为几个阶段？有没有参数在搜索中"意想不到地不重要"？

禁止: 只写"X 步收敛"而不列出 trial 编号和数值。

### §3 参数重要性

必须包含: **Top 10 vs Bottom 10 参数均值对比表**（每行有具体数值 + gap + 解读）+ **≥1 项控制变量验证**（选一个敏感参数，固定其余，单变量扫 ≥4 个值，产出 TR/MDD/Sharpe 对比表）

### §4 市场阶段归因

必须包含: 分阶段表（牛/熊/震荡/复苏，基线 vs 最终，Δ）+ 每阶段一句解读（不是只列数字）

### §5 策略行为诊断

必须包含: 新旧策略的行为对比（持仓分布、交易频率、换仓节奏、扇区权重变化）+ 至少一个"行为模式"发现（如"年均持仓从 3.6 降到 1.9"）

### §6 ETF 四象限

必须包含: 四类全列（核心/狙击手/需排查/边缘），核心和需排查类**必须有 ETF 名称 + P&L + 选中率 + 胜率 + 赔率**的定量数据，不是只写数量

### §7 极端场景与 Bootstrap

必须包含: 极端集中统计（频率、最长持续时间、涉及标的）+ **MDD 期间持仓明细** + **Bootstrap 结果**（median/P5/P1/毁灭概率，来自 analysis.json 的 `bootstrap` 字段）

### §8 局限与后续

必须包含: ≥2 个本次优化的具体局限性 + ≥2 个具体的后续研究方向（非泛泛"继续优化 preset X"）+ 明确的 promote/reject建议

## 九、通用研究方法

这些方法不限于 gam-1，适用于任何参数优化。

### 方法 1：收敛轨迹分析

看 best-so-far 的 trial 序列。TPE 是否在"爬山"？是否有平台期后的跳跃？每次跳跃对应哪些参数变化？讲出"搜索的故事"。

### 方法 2：Top-Bottom 分化

不是比 #1 和 #70——是比 Top 10 和 Bottom 10 的参数均值差异。哪些参数真正区分了优劣，哪些没有。后者往往更有洞察（"原来这个参数不重要"）。

### 方法 3：控制变量验证

单个参数在最优值附近的扫参（固定其他参数）。确认是否真的在凸性顶点。注意：TPE 可能找到了局部最优而非全局最优。

### 方法 4：行为对比

取最优、中游、最差 trial 分别跑完整回测，提取持仓序列、扇区权重时序、交易日志。不看结果（TR），看**行为**（选了什么、什么时候选、持有多久）。

### 方法 5：ETF 四象限

P&L 和选中率两个维度交叉：
- 高 P&L + 高选中 = 核心持仓
- 高 P&L + 低选中 = 狙击手（时机精准但出手少）
- 低 P&L + 高选中 = 需要排查（是不是被错误信号反复引诱）
- 低 P&L + 低选中 = 边缘（策略不用它，没影响）

### 方法 6：极端场景拆解

不要只看均值。看"最惨的时刻"（最大回撤期间持仓）和"最辉煌的时刻"（最快上涨期间持仓）。实盘关心的是极端，不是均值。

## 十、搜索空间设计原则

- 先验证 PARAM_BOUNDS 覆盖基线值（c_sensitivity、f1_ema_period 是历史 bug）
- 已调优的 preset 用窄范围 `[cur×0.5, cur×2.0]`
- 低敏参数（corr<0.15）固定在基线
- 权重参数（w1/w3/w7）sum=100%，最后一个用 residual
- 单周期（6Y）可替代多周期，速度 3 倍且结果一致
- `--universe '*'` 确保全池

### 三派优化目标与约束

`quant_contract.py` 的 `PRESET_OPT_PROFILES` 定义了各 preset 的目标和约束。所有 preset 使用三周期等权 composite（1Y/3Y/6Y 各占 1/3）。

| Preset | 信仰 | metric | 约束 | 初始 preset | 哲学 |
|--------|------|--------|------|-----------|------|
| gam-1/2/3 | 赌徒 | annual_return | mdd,-25（每周期） | 信号通用 + 执行赌徒 | 绝对收益最大化，回撤容忍 |
| zen-1 | 禅修者 | sortino | — | 信号通用 + 执行禅修 | 只惩罚下行波动，允许暴涨 |
| act-1/2 | 精算师 | calmar | bear∈[0.15,0.30] | 信号通用 + 执行精算 | 每单位回撤的回报效率 |

> 初始 preset 的具体数值见本节 §初始 Preset。
> 
> **回测窗口**: 使用滚动 6 年（today - 6Y）。窗口选择依据及新冠 MDD 的处理见 `docs/knowledge/backtest-window.md`。

**三周期等权逻辑**：每个 trial 跑一段 6Y 回测，从 NAV 截取 1Y/3Y/6Y 三段各自算 metric，用 baseline 归一化后取均值。1Y 崩塌的策略在三周期下会被直接惩罚。

**风险控制**：
- 赌徒 mdd,-25 作用于每个周期——不允许 6Y MDD 达标但 1Y MDD 炸裂
- 禅修者 sortino 本身已惩罚下行波动，无需额外约束
- 精算师 bear 约束是哲学底线——任何市场里都不重仓抄底

优化命令：
```bash
# 默认三周期等权 + preset metric + constraint
python scripts/quant_optimizer.py --preset gam-1 --auto-bounds
```

约束语法（可重复）：
- `mdd,-25`：MDD 不低于 -25%（每周期各自检查）
- `bear,0.15,0.30`：ma_bear_pos 必须在 [0.15, 0.30]

## 十一、优化产物归档规范

每次正式参数优化应形成一个自包含目录。使用 `--two-stage` 时目录结构：

```text
research/params/<preset>-YYYYMMDD/
  analysis.json     ← 最终分析数据
  report.md         ← 最终报告
  signal/           ← 信号层原始运行数据
  exec/             ← 执行层原始运行数据
```

| 文件 | 是否提交 | 用途 |
|---|---|---|
| `report.md` | 是 | 人类可读的最终分析报告 |
| `results.json` | 是 | 优化器输出的结构化结果 |
| `analysis.json` | 是 | `optimization_analyzer.py` 输出，作为报告叙事依据 |
| `log.txt` | 是 | 运行过程、参数空间、异常和完成记录 |
| `.optimizer_done` | 可选 | 自动化完成标记；如用于恢复/判断完成态则提交 |
| `optuna.db` | 否 | 本地可复现材料，体积和可变性较高，不提交 |

若同一天多轮搜索，使用 `-v2` / `-v3` / `-v4` 表示搜索轮次，不表示生产策略版本。最终采纳报告应在总览文档中说明“哪一轮被采纳、为什么不是机械取 best trial”。

写报告前必须先生成 `analysis.json`：

```bash
python scripts/optimization_analyzer.py --study <name> --preset <preset> --baseline-preset <baseline> --top-n 3 --output research/params/<dir>/analysis.json
```

报告应基于 `analysis.json` 写结论；不要只从 `optuna.db` 或 Top10 表里抄数字。

## 十二、常见陷阱

- `auto_bounds` 可能给错范围，先手动验证
- `--params` 不加 `--auto-bounds` 时非列表参数走默认值而非基线
- ThreadPoolExecutor 对 CPU 密集回测无效（GIL）
- 权重参数用固定值时不被识别为 weight，不走 residual 调整
- `report.md` 的 Top 表如出现 `0.0000` 指标，说明旧 report generator 字段不完整，应以 `analysis.json` 和最终人工报告为准
