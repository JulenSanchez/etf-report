# Quant Research — 治理框架

三个常驻研究轨道，各自独立推进、独立可停。与需求看板（`plans/`）分离——需求看板管功能级 Bug/Feature，research 管持续探索。

> 本目录记录研究过程、实验结果和 promotion 证据；当前生效参数始终以 `../config/quant_universe.yaml` 为准，工程入口见 `../docs/runbook/v2-quant/overview.md`。

**与 plans/ 需求看板的分工**：research 是探索空间，plans 是交付空间。Promotion 闸门连接二者。

| 场景 | research/ | plans/ (REQ) |
|------|-----------|-------------|
| "F7_k 最优值？" | ✅ 开实验 | — |
| "把 YAML f7_k 改为 3.2" | — | ✅ 提 REQ（引用 research） |
| "新因子有没有用？" | ✅ 开实验 | — |
| "移除 Tuner F4 控件" | — | ✅ 提 REQ（引用结论） |
| TPE 搜索 | ✅ 实验 | ✅ 轻量 REQ 落地 |
| 结论已投产 | → 移入 `promoted/` | REQ→done→Archive |

## 反馈三角

```
        ┌─── pool/ ────┐
        │  标的池选择     │
        └──────┬─────────┘
               │ 池子新增 ETF 类型 → 旧策略可能无法覆盖
               │ 策略需要某类资产 → 池子缺少 → 触发补入
               ▼
      ┌── strategy/ ──┐
      │  策略优化       │
      └───────┬─────────┘
              │ 参数推到边界 → 公式结构可能有问题
              │ 公式改了 → 旧参数作废，重新扫
              ▼
        ┌── params/ ──┐
        │  参数优化     │
        └─────────────┘
```

## 触发机制

| 观察到的现象 | 可能根因 | 触发动作 |
|-------------|---------|---------|
| 参数扫描最优值在可行域边界 | 因子/公式设计有问题 | → `strategy/`，重新审视 |
| 策略在特定行情表现差 | 池子缺少对冲资产 | → `pool/`，候选新 ETF |
| 池子扩容后基线回测退化 | 旧参数在新池子失效 | → `params/`，重新扫 |
| 交叉验证结论矛盾 | 评分公式依赖特定环境 | → `strategy/` + `params/` |

## 停止条件

优化没有"完成"，但可以在以下任一条件满足时暂停：

| 条件 | 动作 |
|------|------|
| 连续 N 次改进幅度 < 阈值 | 搁置，标记 "diminishing returns" |
| 最优参数在可行域内部（非边界） | 结构合理，暂时稳定 |
| 触发了跨轨审视 | 转入另一轨道，本轨暂停 |
| 时间/精力/兴趣转移 | 直接停——TODO 记录当前状态即可恢复 |

## 并行规则

- 三个轨道各自独立，互不阻塞
- 同一轨道内可开多支并行（如 `strategy/position-sizing/` + `strategy/new-factor/`）
- **Promotion 只按基线对比，不按"谁先开始"排队**

## Promotion 闸门

1. 新配置在 1Y/3Y/6Y 三窗口跑基线回测（等权）
2. 不低于当前生产配置 → promotion
3. 有退化 → 不阻塞升级，但写 trigger 到对应轨道的 TODO
4. **Promotion 记录写入 `promoted/README.md`**（日期、结论、来源、对应 REQ、落地位置）
5. 已投产的研究文档移入 `promoted/` 目录

## 自动化工具

参数优化推荐使用统一优化器 `scripts/quant_optimizer.py`（替代手工 sweep 脚本）：

```bash
# 见 docs/runbook/v2-quant/overview.md 完整用法
python scripts/quant_optimizer.py --preset daily_aggressive --strategy bayesian --auto-bounds --n-trials 100
```

支持 grid / random / bayesian (Optuna TPE) 三种策略，输出结构化 results.json + report.md。

## 目录公约

```
research/
├── README.md           ← 本文件（治理框架 + plans边界规则 + Git提交规则）
├── _template/          ← 新建研究项目时复制此骨架
│   ├── README.md       ← 方法论 + 假说 + 结论
│   └── results.json    ← 摘要指标（建议 < 200KB）
├── promoted/           ← 已投产的研究结论（Promotion Log）
│   ├── README.md       ← 投产记录表
│   ├── persona-declarations-*.md
│   └── persona-baseline-*.md
├── pool/               ← 标的池选择
│   ├── README.md       ← 当前池子、候选列表、DEAD_ENDS
│   └── ...
├── strategy/           ← 策略优化
│   ├── README.md       ← 当前策略、历史探索、DEAD_ENDS
│   ├── dynamic-C/      ← CS 参数网格搜索
│   ├── kelly/          ← 凯利 Bootstrap 分析
│   ├── REQ-189/        ← 后视镜最优收益 (2026-05)
│   └── ...
└── params/             ← 参数优化
    ├── README.md       ← 当前最优参数、扫描历史、DEAD_ENDS
    ├── F7-optimization/        ← F7 因子历史优化
    └── ...
```

### Git 提交规则（由 `.gitignore` 自动执行）

| ✅ 提交 | ❌ 仅本地（脚本可重新生成） |
|--------|---------------------------|
| `README.md`（研究结论 + 方法论） | `*.csv`（NAV 曲线、回测输出） |
| `results.json`（摘要指标） | `*.db`（Optuna 超参搜索缓存） |
| 小型数据文件（< 200KB .json） | `__pycache__/` |
| | `*.py` 研究脚本 |

> 原则：研究目录自包含，但只有**研究结论**进仓库。中间产物由此处的 `.py` 脚本重新生成。`.gitignore` 是自动门禁，本段是说明。
>
> 新建研究项目：复制 `_template/` → `research/<新项目名>/`，写 `README.md` + `results.json`。

### 本地数据保留规则

CSV/DB 不进 Git，但本地是否保留取决于对应因子的状态：

| 因子状态 | CSV/DB 中间数据 | 理由 |
|---------|----------------|------|
| 仍在活跃使用（F1/F3/F7） | ✅ 保留 | 新课题预研时可参考现有回测数据 |
| 已退役（F2/F4/F5/F6） | ❌ 删除 | 框架已变，旧数据零参考价值 |
| 框架大版本升级（v3→v4） | 按因子状态逐项判断 | 以当前 `quant_universe.yaml` 活跃因子清单为准 |

> 清理时机：因子退役时、大版本发布后。手动执行，不需要每次提交都检查。

## 与需求看板的边界

| | `plans/` (需求看板) | `research/` (本目录) |
|------|------|------|
| 追踪对象 | 功能/Bug/Feature | 持续优化/探索 |
| 生命周期 | 有明确完成态 | 长期开放 |
| 产出 | 代码变更 | 数据结论 + promotion |
| Bug | ✅ 由需求看板接管 | ❌ research bug → 提 BUG 号 |
| 文档 | REQ-XXX.md | README + 报告 + JSON |
