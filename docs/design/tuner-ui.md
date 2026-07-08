# Tuner UI 设计文档

> 本文是 Tuner 前端的所有 UI 设计约束的单一事实源，涵盖布局、交互、配色、组件。不追求一次性完整——每次 UI 改动 REQ 完成后补充对应章节。
>
> 旧文件 `tuner-layout.md` 已被本文取代。

## §1 基准环境

| 参数 | 值 |
|------|------|
| 屏幕物理分辨率 | 3840 × 2160 |
| OS 缩放 | 150% |
| CSS 有效分辨率 | **2560 × 1440** |
| 浏览器缩放 | 100% |
| 页面视口（实际可用） | 2552 × 1274（减去浏览器 chrome） |

所有尺寸均为 **CSS 像素**（`getBoundingClientRect` 返回值）。

## §2 布局

### 2.1 布局哲学

- **左参数、右回测**：参数调优是输入，回测结果是输出，左右分栏符合"调参→看结果"的心智模型
- **上汇总、下明细**：策略业绩在上（快速判断），ETF/快照在下（深入分析）

### 2.2 布局结构

```
┌────────────┬──────────────────────────────────────────┐
│  左侧参数   │              右侧回测结果                   │
│  360px 固定 │             2192px 弹性                    │
│            │  ┌──────────────────────────────────────┐ │
│  策略Preset │  │  指标卡片 (2行×5列, 固定网格)          │ │
│  因子配置   │  ├──────────────────┬───────────────────┤ │
│  仓位控制   │  │  NAV 走势图      │  DD 回撤图         │ │
│  时间窗口   │  │  1261×320        │                    │ │
│  标的筛选   │  ├──────────────────┴───────────────────┤ │
│            │  │  ETF 快照 (左)    │  调仓快照 (右)     │ │
│            │  │  1282×518         │  855×(剩余高度)    │ │
│            │  └──────────────────┴───────────────────┘ │
└────────────┴──────────────────────────────────────────┘
        2552px（页面总宽）
```

### 2.3 容器预算表

实测数据（2026-07-02, gam-0 回测结果渲染后）：

| 容器 | ID | 宽度 | 高度 | 位置 | 备注 |
|------|-----|------|------|------|------|
| 页面总容器 | `tuner-panels` | **2552** | **1240** | top=0 left=0 | 根容器 |
| 左侧参数面板 | `tuner-panel-left` | **360** | 1240 | left=0 | 固定宽度，`overflow-y:auto` 内滚动 |
| 右侧结果区 | `tuner-panel-right` | **2192** | 1240 | left=360 | 弹性宽度，撑满剩余空间 |
| 结果内容区 | `results` | 2137 | 1180 | top=63 left=380 | 含 30px padding，实际内容宽~2077 |
| 指标卡片区 | 10× `.metric-card` | ~2077 | **128** | top=63 | 2 行 × 5 列 CSS Grid，实测高度 128px（不含翻页箭头 padding） |
| NAV 走势图 | `nav-chart` | 1261 | **320** | top=266 left=391 | ECharts 固定高度 |
| ETF 详情快照 | `tuner-kline-section` | 1282 | **518** | top=719 left=380 | 底部左栏，K 线 + 贡献明细 |
| 调仓快照 | `tuner-snapshot-section` | 855 | 1180 | top=63 left=1676 | 底部右栏，占据整个右侧高度 |

### 2.4 约束规则

1. **总高宽不变**：页面总容器高度 = 视口高度，不出现页面级滚动条。溢出由子容器内部滚动消化。
2. **侧栏固定宽度**：`#tuner-panel-left` = 360px，内容超出一屏时用 `overflow-y:auto` 而非扩展宽度。
3. **卡片网格占位**：指标卡片区固定 2×5 网格（10 slot），空缺 slot 由占位卡填补，增减卡片不改变列数。
4. **图表区高度固定**：`#nav-chart` = 320px。修改图表需在固定高度内调整内部 margin/padding。
5. **底部双栏**：左栏（ETF 快照）≈1282×518，右栏（调仓快照）≈855×(剩余高度)。`flex-wrap: nowrap`。
6. **容器间零溢出**：所有一级子元素 `sum(width) ≤ #tuner-panels.width`，`sum(height) ≤ #tuner-panels.height`。新增容器需从现有容器回收空间。

## §3 图表交互规则

### 3.1 联动关系

- **NAV 图 ↔ DD 图**：共享 `tuner-zoom` groupId，缩放/平移联动。两图宽度必须一致，保证 X 轴日期对齐。
- **NAV 图 → ETF 快照 + 调仓快照**：点击 NAV 图上的日期，快照跳转到该日前最近一次调仓。
- **DD 图应与 NAV 图保持相同宽度**：DD 图是 NAV 图的回撤维度补充，左右宽度对齐保证 tooltip cross-hair 在日期上同步。

### 3.2 图表尺寸约束

- 新增图表时，如果与现有图表有联动关系，宽度必须与联动对象一致
- 无联动关系的图表可以灵活排列（如并排）
- 所有图表高度由容器预算表决定，新增图表不得扩展容器总高

## §4 配色系统

### 4.1 架构

所有语义色通过 CSS 自定义属性（`:root` 块）集中定义，HTML/CSS/JS 通过 `var(--name)` 或 `TC.name` 引用。**改主题色只需改 `:root` 块和 `TC` 对象中的色值**，无需搜索替换。

- CSS 侧：`templates/tuner.html` 内 `<style>` 顶部的 `:root { ... }` 块（~58 行）
- JS 侧：`<script>` 顶部的 `var TC = { ... };` 对象（~33 行）
- 两者必须同步——JS 对象是 CSS 变量的镜像，供 JS 内联样式引用

### 4.2 CSS 变量表

#### 强调/交互
| 变量 | 色值 | 用途 |
|------|------|------|
| `--accent` | `#3b82f6` | 主强调色：active 边框、section 标题、滑块 thumb、选中态 |
| `--accent-light` | `#60a5fa` | 浅强调：tab active 文字、slider value、链接色 |
| `--accent-bg` | `rgba(59,130,246,0.12)` | 强调态半透明背景 |
| `--accent-border` | `rgba(59,130,246,0.15)` | 强调态半透明边框 |
| `--accent-soft` | `rgba(59,130,246,0.10)` | 弱强调背景 |
| `--blue-dark` | `#2563eb` | 按钮/控件深蓝（hover/pressed） |
| `--blue-darker` | `#1d4ed8` | 按钮更深蓝 |

#### 语义色
| 变量 | 色值 | 语义 |
|------|------|------|
| `--positive` | `#10b981` | 正向：盈利、买入 NEW、高置信度、权重达标 |
| `--negative` | `#ef4444` | 负向：亏损、卖出 OUT、MDD、低置信度 |
| `--warning` | `#f59e0b` | 警告/中性：刷新按钮、进度条、检查点、中置信度、RSI |
| `--highlight` | `#fbbf24` | 高亮：前沿选中点、高集中度、Z=0 参考线 |

#### 表面/背景
| 变量 | 色值 | 用途 |
|------|------|------|
| `--bg-body` | `#0f1419` | 页面底色 |
| `--bg-panel` | `#1a2332` | 卡片/面板背景 |
| `--bg-hover` | `#1e293b` | hover 态、行交替、细分隔线 |
| `--bg-active` | `#1e3050` | active 卡片/选中行背景 |
| `--bg-input` | `#1e2d3d` | 输入框、进度条 track、因子配置背景 |

#### 边框
| 变量 | 色值 | 用途 |
|------|------|------|
| `--border` | `#2a3a4a` | 主边框：面板、卡片、表格、图表轴线 |
| `--border-light` | `#1e293b` | 细分隔线（与 `--bg-hover` 同色） |
| `--border-muted` | `#334155` | 弱边框：toggle pill、快捷键、disabled 态 |
| `--border-disabled` | `#374151` | 更弱边框：disabled 按钮 |

#### 文字
| 变量 | 色值 | 用途 |
|------|------|------|
| `--text-heading` | `#f0f0f0` | 标题、卡片 value |
| `--text-body` | `#e0e0e0` | 正文、slider label、图表 tooltip |
| `--text-secondary` | `#94a3b8` | 副文本、school header、K 线价格线 |
| `--text-muted` | `#6b7280` | 弱文本：axis label、表头、disabled 态 |
| `--text-dim` | `#4b5563` | 最弱文本：placeholder、锁定参数值 |
| `--text-link` | `#60a5fa` | 链接/代码（同 `--accent-light`） |

#### 按钮
| 变量 | 色值 | 用途 |
|------|------|------|
| `--btn-save` | `#22c55e` | Save 按钮边框/文字（绿） |
| `--btn-save-hover` | `rgba(34,197,94,0.1)` | Save 按钮 hover 背景 |
| `--btn-refresh` | `#f59e0b` | Refresh 按钮边框/文字（同 `--warning`） |
| `--btn-refresh-hover` | `rgba(245,158,11,0.1)` | Refresh 按钮 hover 背景 |

#### 图表
| 变量 | 色值 | 用途 |
|------|------|------|
| `--chart-nav` | `#3b82f6` | NAV 策略曲线 |
| `--chart-bench` | `#f59e0b` | 基准线（沪深300） |
| `--chart-eqwt` | `#8b5cf6` | 等权持有基准线 |
| `--chart-mdd` | `#ef4444` | 回撤线/区域填充 |

#### 流派主题色（预留，尚未应用）
| 变量 | 色值 | 流派 |
|------|------|------|
| `--school-gambler` | `#f97316` | 赌徒 |
| `--school-zen` | `#14b8a6` | 禅修者 |
| `--school-actuary` | `#6366f1` | 精算师 |

### 4.3 JS 色表（`TC` 对象）

与 CSS 变量一一对应，供 JS 内联样式引用。键名使用 camelCase：

```javascript
var TC = {
  accent:       '#3b82f6',   // --accent
  accentLight:  '#60a5fa',   // --accent-light
  positive:     '#10b981',   // --positive
  negative:     '#ef4444',   // --negative
  warning:      '#f59e0b',   // --warning
  highlight:    '#fbbf24',   // --highlight
  // ... 完整列表见 tuner.html
};
```

JS 中引用示例：`el.style.color = TC.positive;`

### 4.4 不改动区

以下色值逻辑复杂（多色渐变、阈值阶梯、动态计算），保留局部硬编码：

| 区域 | 原因 |
|------|------|
| 热力图 diverging 色阶 (`#8b1515`…`#3cdb78`) | 9 级渐变，已在 `visualMap.inRange.color` 集中定义 |
| 涨跌分布 bin 色阶 | 7 级灰度渐变 |
| 数据新鲜度 badge 背景 | 3 个独立 bg+text 组合（confirmed/intraday/stale） |
| 扇区/Group1 色表 | 已在 `GROUP1_COLORS` / `HM_SEC_COLOR` 集中定义 |
| 因子曲线色表（F1/F3/F7 guide curves） | 每图 3-5 条曲线，已在各自 `curves` 数组中集中定义 |
| 动态阈值色（`pos >= 30 ? '#fbbf24' : ...`） | 条件判断逻辑，替换为 `TC.xxx` 仍需保持逻辑，已替换常量部分 |

### 4.5 主题基调

深色主题，背景色 `var(--bg-body)` = `#0f1419`，卡片/面板底色 `var(--bg-panel)` = `#1a2332`。

## §5 组件模式

### 5.1 指标卡片 `.metric-card`

- 固定网格 2×5，每卡 `label` + `value` 结构
- 颜色语义按 §4.2 分配
- tooltip 仅展示公式右侧（RHS），不包含主观评判

### 5.2 参数滑块 `.slider-group`

- 左侧面板内，`label` + `range input` + `value display`
- 单位标注在 label 或 value 后

### 5.3 按钮与 Toggle Pill

#### 主操作按钮

- Run Backtest / Save YAML：`var(--accent)` 蓝底白字
- Refresh / Meta：`var(--btn-refresh)` 边框

#### 切换/选项按钮

- 周期、频率、流派：暗底边框，选中态高亮

#### Debug Toggle Pill

- **DOM**: `<span id="toggle-debug" class="toggle-pill" title="回测调试快照">` (tuner.html:683) + 隐藏 checkbox `#chk-debug` (tuner.html:685)
- **触发方式**: 点击 pill → 切换 `.on` 视觉态 + `chk-debug.checked`；实际生效发生在下次点 "Run Backtest"
- **API 链路**: `POST /api/run` 携带 `params.debug=true` → `quant_tuner.py:1326` `return_debug=bool(params.get("debug"))` → `run_backtest(return_debug=True)`
- **产出物**: `data/quant/debug_tuner.json`，格式 `{"count": N, "snapshots": [...]}`
- **交互行为**: pill 是"开关 + 下次回测生效"，非即时；off 时不出新文件；旧文件���自动清除
- **边界约束**: 仅诊断用，不影响 nav_df / signal_history；字段结构详见 `backtest-engine.md` §8.4
- **配色**: 复用 `--border-muted` / `--accent`（不新增色）
- **什么时候用**: 信号不一致排查（前端 vs 脚本结果不同）/ 因子异常诊断 / 持仓偏差排查
- **怎么读**:
  ```bash
  python -c "import json; d=json.load(open('data/quant/debug_tuner.json')); print(json.dumps(d['snapshots'][-1], indent=2, ensure_ascii=False))"
  ```

#### 数据新鲜度 Badge

- **DOM**: `<span id="data-status">` (tuner.html:694) + `.data-badge` 三态 class
- **触发方式**: 页面加载时自动调 `GET /api/data_status`；点 Refresh 按钮后刷新
- **三态语义**:
  - `confirmed` (绿): CSV 含最近交易日收盘数据
  - `intraday` (黄): 仅有盘中 cache，CSV 未更新
  - `stale` (红): 数据滞后超过 1 个交易日
- **配色**: 复用 `--positive` / `--warning` / `--negative`

### 5.4 Tooltip

- 深色半透明底 `rgba(10,25,47,0.95)`
- 蓝色边框 `rgba(59,130,246,0.2)`
- 字体 11px `var(--text-body)`

### 5.5 进度条

- **DOM**: `#tuner-progress-bar` + `#tuner-progress-text` (tuner.html:687-690)
- **触发方式**: 回测进度回调，实时更新百分比
- **交互行为**: 两段式 — Pass 1（因子预计算，~28%）+ Pass 2（每日迭代，~69%），动态权重按实测耗时分配（REQ-343）
- **配色**: track 用 `--bg-input`，fill 用 `--warning`

### 5.6 热力图

- **DOM**: `#hm-chart` (tuner.html:1126)
- **API**: `GET /api/heatmap_data?lookback=N`
- **交互行为**: 5/20 日切换、垂直/水平滚动滑块、重置按钮
- **配色**: diverging 色阶 9 级渐变（`#8b1515`…`#3cdb78`，见 §4.4 不改动区）

### 5.7 涨跌分布图

- **DOM**: `#dist-chart` (tuner.html:983)
- **交互行为**: 极值卡点击跳转 `jumpToDistDate`；7 级灰度 bin 展示分布
- **配色**: 7 级灰度渐变（见 §4.4 不改动区）

### 5.8 前沿点选择器

- **DOM**: 动态生成 `frontier-chart-{sid}`（tuner.html:2472+）
- **API**: `GET /api/frontier`
- **交互行为**: 点击前沿点 → 加载该点参数到左侧 slider → 可直接 Run Backtest
- **配色**: `--highlight` 高亮选中点；gambler 自动注入 gam-0 参考点

### 5.9 ETF 详情区

- **DOM**: `#tuner-kline-section` (tuner.html:1016)
- **交互行为**: K 线回放、十大重仓 tab、日/周 K 切换、贡献 grid
- **联动**: 点击 NAV 图日期 → 跳转到该日最近调仓的 ETF 详情
- **边界**: 贡献 grid 的计算逻辑见 `etf-contribution.md`

### 5.10 调仓快照表

- **DOM**: `#tuner-snapshot-section` (tuner.html:1036)
- **交互行为**: 8 列可排序（`onSnapSort`）、4 个 snap 指标卡、扇区过滤（全选/全不选/反选）
- **配色**: 复用语义色（`--positive` 买入 / `--negative` 卖出）

### 5.11 右侧视图切换

- **DOM**: 4 个 tab（guide / results / heatmap / datamgmt）
- **交互行为**: 点击切换视图，同时只有一个 tab 激活；各 tab 内容由对应组件定义
- **边界**: guide = 使用说明；results = §5.1-5.4 + §5.9-5.10；heatmap = §5.6；datamgmt = §5.12

### 5.12 数据管理视图

- **DOM**: `dm-*` 全套控件
- **交互行为**: 日期范围、频率、字段、扇区过滤、删除/重拉/补全、矩阵滚动
- **边界**: 详细设计见 `data-management-panel.md`，本文不重复

## §6 已知偏差

- **调仓快照右栏比左栏高**：`#tuner-snapshot-section` 高度 1180px，与 `#results` 相同。实际视觉效果是右栏略高于左栏 ETF 快照（518px）。该偏差在当前视口下不触发滚动条，属于可接受范围。
- **DD 图与 NAV 图宽度不一致**：当前 DD 图 `width:100%` 实际渲染宽度可能与 NAV 图不同。由于 tooltip cross-hair 依赖相同 X 轴对齐，DD 图宽度应显式约束为与 NAV 图一致（≈1261px）。

## §7 修改指南

任何 Tuner UI 改动 REQ 必须先回答：

1. 是否改变容器尺寸？→ 更新 §2.3 预算表
2. 是否增减卡片/图表？→ 检查网格 slot / 占位卡影响
3. 新增图表是否与现有图表有联动关系？→ 宽度必须一致
4. 是否新增容器？→ 说明空间从哪个现有容器回收
5. 是否引入新颜色？→ 补充 §4
6. 视口变小时是否降级？→ 说明 `@media` 降级策略

## §8 参考

- `templates/tuner.html` — 实际 DOM 结构
- `plans/REQ-347.md` — 最近一次卡片精简（15→10, 两页合一）
- `plans/REQ-345.md` — 布局框架 REQ
- `plans/REQ-346.md` — 涨跌分布 UI REQ
