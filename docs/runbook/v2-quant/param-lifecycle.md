# 参数生命周期管理

> **触发词**: "新增参数" "加一个参数" "删除参数" "退役参数" "修改参数" "改参数定义" "参数变更"

本文档定义搜索参数的完整生命周期：**新增 → 修改 → 退役**。每一步都有必改文件清单 + 验证命令。

**前置知识**：参数架构见 `docs/design/backtest-engine.md` §11（系统级修改清单）和 `docs/design/overview.md`（参数映射集中化）。本文是这些设计文档的**操作级补充**——告诉你具体改哪些文件、按什么顺序。

**适用范围**：
- **搜索参数**（`PARAM_BOUNDS` 中 `searchable: true`）：TPE 会优化的参数，如 `band_sensitivity`、`concentration`
- **非搜索参数**（`searchable: false`）：固定值参数，如 `financing_rate_annual`、`rebalance_freq`

---

## 一、新增参数

> 案例：v3.10.0 新增 `band_sensitivity`，17 个点里漏了 YAML 预设和优化器 backfill → 旧 pool trial 重验证全丢、种子读不到新参。

### 搜索参数（17 个必改点）

#### 定义层（5 处）

| # | 文件 | 改动 | 说明 |
|---|------|------|------|
| 1 | `quant_contract.py` — `PARAM_SCHEMA` | 加 `{"key": "...", "label": "...", "unit": "...", "engine_path": "..."}` | Tuner 前端渲染控件用；`unit` 决定 UI↔引擎值转换公式 |
| 2 | `quant_contract.py` — `PARAM_BOUNDS` | 加 `{"type": "continuous", "min": ..., "max": ..., "step": ...}` | TPE 搜索空间定义 |
| 3 | `quant_contract.py` — `_REQUIRED_PARAMS` | 加参数名到 frozenset | 缺参时 `tuner_params_to_config_override` 抛 ValueError |
| 4 | `config/defaults.yaml` | 加默认值 | 唯一默认值来源 |
| 5 | `quant_contract.py` — `INITIAL_PRESETS` | 加 gambler/zen/act 三派初始值 | 冷启动种子使用 |

#### 转换层（4 处）

| # | 文件 | 改动 | 说明 |
|---|------|------|------|
| 6 | `quant_contract.py` — `tuner_params_to_config_override` | UI→引擎值转换 + fallback | `_as_float(params.get("new_param"), defaults_val) / scale` |
| 7 | `quant_contract.py` — `preset_to_tuner_params` | 引擎→UI 值反向转换 + fallback | 乘以 scale，fallback 到 defaults.yaml |
| 8 | `quant_contract.py` — `seed_params_from_presets` | 从 YAML 预设提取参数 | 冷启动种子关键路径 |
| 9 | `quant_contract.py` — `build_frontier_output` | 前沿输出 + 旧 trial backfill | 前沿 JSON 包含该参数 + 缺参时填默认值 |

#### 预设 + UI 层（4 处）

| # | 文件 | 改动 | 说明 |
|---|------|------|------|
| 10 | **`config/quant_universe.yaml`** — 全部 7 个预设 | 每个 preset 的对应 section 加该参数 | ← **最容易漏** |
| 11 | `templates/tuner.html` — HTML slider | `<input type="range" id="new_param">` | id 必须与 PARAM_SCHEMA key 一致 |
| 12 | `templates/tuner.html` — JS `getTunerParams()` | `new_param: parseFloat($id('new_param').value)` | 前端读值 |
| 13 | `templates/tuner.html` — JS `setParams()` | `setSlider('new_param', p.new_param)` + display update | 前端写值 |

#### 优化器 + 引擎 + 报告层（3 处）

| # | 文件 | 改动 | 说明 |
|---|------|------|------|
| 14 | `scripts/iterative_optimizer.py` — backfill block | 旧 pool trial 缺参时填默认值 | 在 `main()` 的 pool 加载后、cold start 前 |
| 15 | `scripts/quant_backtest.py` — 引擎读取 + 逻辑 | `cfg.get("new_param", default)` + 业务逻辑 | 如果参数影响运行时行为 |
| 16 | `scripts/update_report.py` — `default_quant_preset_params()` | 加 fallback 值 | 正式页报告生成用 |

#### 测试层（1 处）

| # | 文件 | 改动 |
|---|------|------|
| 17 | `tests/test_quant_contract.py` — `sample_params()` | 加该参数 + 测试值 |

### 非搜索参数

跳过 #2（PARAM_BOUNDS 搜索空间）和 #14（优化器 backfill）。覆盖其余 15 个位置。

### 验证

```bash
# 1. 转换链路完整性
python -c "
from etf_report.core.quant_contract import tuner_params_to_config_override, seed_params_from_presets
ov = tuner_params_to_config_override({...所有参数含新参...})
seeds = seed_params_from_presets('gambler')
print('OK' if all('new_param' in s.get('params',{}) for s in seeds) else 'FAIL')
"

# 2. 回测不退化
python scripts/quant_backtest.py --preset gam-0 --start 2020-07-03

# 3. 测试套件
python -m pytest tests/test_quant_contract.py -q
```

---

## 二、修改参数

修改一个已有参数的定义，影响面取决于**改了什么**。

### 分类矩阵

| 改了什么 | 影响面 | 必改文件 |
|---------|--------|---------|
| **默认值** | 小 | `defaults.yaml` |
| **搜索范围**（min/max/step） | 中 | `PARAM_BOUNDS` + `INITIAL_PRESETS` |
| **单位/缩放**（`unit` in SCHEMA） | 大 | SCHEMA + 转换函数（#6 + #7）+ Tuner 控件 |
| **语义/重命名**（`engine_path` 变了） | 大 | SCHEMA + YAML presets + engine 消费点 |
| **所属 section**（如从 `position` 移到 `scoring`） | 最大 | 几乎全部 17 个点 |
| **searchable ↔ 非 searchable** | 中 | PARAM_BOUNDS + 优化器 backfill |

### 修改默认值

只改 `config/defaults.yaml`。验证：

```bash
python tests/test_defaults.py
python scripts/quant_backtest.py --preset gam-0 --start 2020-07-03  # 确认不退化
```

### 修改搜索范围

改 `PARAM_BOUNDS` 中的 `min`/`max`/`step`。同步更新：
- `INITIAL_PRESETS`（如果初始值不在新范围内）
- Tuner HTML slider 的 `min`/`max`/`step` 属性（#11）

验证：跑一轮优化确认 TPE 在新范围内正常采样。

### 修改单位/缩放

**这是最容易引入 bug 的修改类型。** 涉及 UI↔引擎值的转换公式。

必须逐项检查：
1. `PARAM_SCHEMA` 的 `unit` 字段改了吗？
2. 转换函数（#6 `tuner_params_to_config_override`）的除数是新 scale 吗？
3. 反向转换（#7 `preset_to_tuner_params`）的乘数是新 scale 吗？
4. Tuner slider 的 `min`/`max`/`step` 是新 scale 下的值吗？
5. `defaults.yaml` 的值是新 scale 下的值吗？
6. 全部 7 个 YAML preset 的值需要重算吗？
7. `seed_params_from_presets`（#8）的乘法对了吗？
8. `build_frontier_output` 的 backfill 默认值对了吗？

验证：用同一组 UI 参数，对比新旧代码生成的 `config_override` 是否一致。

### 重命名参数

参数名（key）变了 = **先做新增再做退役**，不要直接改名字。

1. 按 §一 新增新名字的参数（17 个点）
2. 迁移所有 YAML preset 的值到新名字
3. 跑一轮优化确认新参正常工作
4. 按 §三 退役旧名字

### 修改后验证（通用）

```bash
# 转换链路
python -c "from etf_report.core.quant_contract import tuner_params_to_config_override; ..."

# 回测一致性（修改前后 gam-0 结果应一致，除非有意改变行为）
python scripts/quant_backtest.py --preset gam-0 --start 2020-07-03

# 全量测试
python -m pytest tests/ -q
```

---

## 三、退役/删除参数

> 案例：F2/F4/F5/F6 退役（2026-05），参考 `research/strategy/2026-05-28-research-archive.md` §8

退役一个参数不等于"删掉代码"。参数在 pool.json、frontier JSON、历史回测记录中仍有残留——硬删会破坏可复现性。

### 退役流程

#### 1. 裁决

退役一个参数必须有明确理由，记录在 REQ 中：

- **冗余**（如 F2 与 F1 相关 0.85，无独立信息）
- **无效果**（如某个 sensitivity 参数在所有 preset 中都用默认值，从未被优化选中）
- **被替代**（新参数覆盖了旧参数的功能）

#### 2. 代码清退（逆向 17 点 checklist）

按新增清单的逆序清理：

| # | 文件 | 操作 |
|---|------|------|
| 1 | `PARAM_SCHEMA` | 移除该参数条目 |
| 2 | `PARAM_BOUNDS` | 移除（或标记 `searchable: false` 保留占位） |
| 3 | `_REQUIRED_PARAMS` | 从 frozenset 移除 |
| 4 | `defaults.yaml` | 移除该行（如果 preset 都不引用） |
| 5 | `INITIAL_PRESETS` | 移除初始值 |
| 6 | `tuner_params_to_config_override` | 移除该参数的转换代码 |
| 7 | `preset_to_tuner_params` | 移除反向转换代码 |
| 8 | `seed_params_from_presets` | 移除提取逻辑 |
| 9 | `build_frontier_output` | 移除前沿输出中的该参数 + 移除 backfill 逻辑 |
| 10 | `quant_universe.yaml` 全部 7 个预设 | 移除该参数行 |
| 11 | `tuner.html` slider | 移除 `<input>` 控件 |
| 12 | `tuner.html` JS `getTunerParams()` | 移除读取行 |
| 13 | `tuner.html` JS `setParams()` | 移除设置行 |
| 14 | `iterative_optimizer.py` backfill | 移除 backfill 逻辑 |
| 15 | `quant_backtest.py` 引擎 | 移除读取 + 相关逻辑（注意：可能影响回测结果！） |
| 16 | `update_report.py` | 移除 fallback 值 |
| 17 | `tests/test_quant_contract.py` | 移除 `sample_params()` 中的该参数 |

#### 3. 回测兼容性处理

退役参数的**引擎消费逻辑**（#15）是最危险的一步。如果引擎代码依赖该参数：

```python
# ❌ 直接删掉 → 旧 preset 回测报错
# ✅ 保留读取 + 默认值 fallback，逻辑分支不再触发
old_value = cfg.get("retired_param", safe_default)
# 退役参数的逻辑分支已移除
```

旧 preset、旧 pool trial 中仍可能包含退役参数。处理策略：

- **向前兼容**：引擎读取时设 `safe_default`，不报错也不使用
- **pool 不强制清洗**：pool.json 中的旧 trial 可以保留退役参数的 key——`tuner_params_to_config_override` 忽略未知 key 即可
- **frontier 不强制重生成**：前沿 JSON 中的退役参数 key 保留，不影响 Tuner 展示

#### 4. 文档登记

退役后必须在以下位置登记：

| 位置 | 登记内容 |
|------|---------|
| `docs/design/factors.md` §5.4 "已退役因子" | 参数名 + 退役日期 + 原因 + 替代方案 |
| `research/strategy/` 对应日期归档 | 退役裁决的完整证据链 |
| `plans/Board.md` | 如有关联 REQ，更新状态 |
| `docs/runbook/audit.md` §4 "退役清理" 检查点 | 退役后审计会自动检查残留 |

#### 5. 验证

```bash
# 1. 旧 preset 回测不报错
python scripts/quant_backtest.py --preset gam-0 --start 2020-07-03

# 2. 测试套件全绿
python -m pytest tests/ -q

# 3. grep 退役参数名 — 只在"已退役"登记处出现，其他位置已清理
rg "retired_param_name" --type-add 'code:*.{py,js,yaml,html}' -t code -t yaml

# 4. audit.md §4 退役清理检查
```

---

## 四、关联文档

| 文档 | 与本指南的关系 |
|------|--------------|
| `docs/design/overview.md` | 参数映射架构总览；新增参数四项对齐 |
| `docs/design/backtest-engine.md` §11 | 系统级修改清单（成交口径/因子/仓位/preset）；本文是操作补充 |
| `docs/design/factors.md` §5.4 | 已退役因子登记表 |
| `docs/runbook/v2-quant/optimization.md` | 优化器使用手册；默认值规范 |
| `docs/runbook/v2-quant/preset-change.md` | Preset 投产流程（研究→裁决→落地→收口） |
| `docs/runbook/audit.md` §4 | 退役清理审计检查点 |
| `plans/Board.md` | 当前活跃 REQ、版本规划 |

---

## 五、快速索引

| 我想... | 看这里 |
|---------|--------|
| 加一个新参数 | §一 |
| 改一个参数的默认值 | §二 → "修改默认值" |
| 改一个参数的搜索范围 | §二 → "修改搜索范围" |
| 改参数的单位/缩放公式 | §二 → "修改单位/缩放" |
| 给参数换个名字 | §二 → "重命名参数" |
| 删掉一个没用的参数 | §三 |
| 了解参数的架构设计 | `docs/design/overview.md` |
| 把优化结果写入生产 preset | `docs/runbook/v2-quant/preset-change.md` |
| 跑一轮参数优化 | `docs/runbook/v2-quant/optimization.md` |
