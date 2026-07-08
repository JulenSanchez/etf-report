# 数据管理面板 — 设计文档

> 对应 REQ-355。实现细节、布局预算、状态机。

## 布局结构

```
panel-right (padding:20px; overflow-y:auto)
  view-switcher (44px)
  right-view-datamgmt (.dm-flex-col)
    dm-toolbar (~30px)
    dm-matrix-wrap (calc(100vh - 180px))
      Row 1: etf-col(140px) | grid-area(flex:1) | vslider(12px)
      Row 2: h-slider (margin-left:140px, 10px)
    status-bar (~28px, 含 sector 图例)
    dm-toast (fixed, bottom-right, pointer-events:none)
```

## 数据格状态机

```
d in csv_dates?
  ├─ Yes → status=csv (绿)
  └─ No  → d == intraday_date AND code in intraday_cache?
              ├─ Yes → halted?
              │         ├─ Yes → status=halted (灰+⏸)
              │         └─ No  → status=intraday (橙+粗体)
              └─ No  → status=missing (灰)
```

注：CSV 检查优先于 intraday 检查。盘后 CSV 写入当天数据后，intraday 状态不再出现——这是正确行为。

## 异常检测

- 日收益率 = `(close - prev_close) / prev_close`
- 阈值：所有 ETF 统一 20%（含 QDII）
- 前端：`.dm-cell.anomaly-surge`（红底脉冲）/ `.anomaly-plunge`（绿底脉冲）

## 选择交互

- 拖拽：mousedown 记录起点 → mousemove 矩形选区 → mouseup 结束
- 行头点击：toggle 该行所有格
- 列头点击：toggle 该列所有格
- 板块图例点击：toggle 该板块所有 ETF×全部日期
- 操作按钮根据 `dmSelected` 数量决定 enabled/disabled

## Toast 通知

实现参考 `资产评审台` 的 `showToast`：
- 单元素 `#dm-toast`，CSS transition 0.25s
- `translteY(60px)` → `translteY(0)` 滑入
- `setTimeout` 2.8s 后滑出
- `clearTimeout` 防抖——连续触发时替换旧消息
- `pointer-events: none` 不拦截鼠标

## Slider

参考涨跌热力 `hm-hslider` + `hm-vslider`：
- 横条：`margin-left:140px` 与数据区左对齐
- 竖条：右侧 12px 宽，viewport overflow:hidden
- `vp.scrollLeft`/`scrollTop` 同步到 handle 位置

## 数据层/字段切换

两级工具栏：
- **一级（数据层）**：`[日线] [周线] [因子]`。`dmFreq` 状态，反映数据加工链路：API→日线→周线→因子
- **二级（字段）**：
  - 日线/周线：`[收盘价] [成交量] [成交额]`
  - 因子：`[F1] [F3] [F7]`

### 因子模式

- 数据源：`data/quant/.factor_cache/fc_{sha256}.pickle`（缓存 key 设计见 `backtest-engine.md` §12）
- 每个 pickle 含 `daily_dates` + `f1`/`f3`/`f7` 数组（逐日粒度）
- 无缓存时显示 missing，可通过"强制更新"（删缓存+回测重算）或"补全空缺"（只补缺失）重建
- 后端 API：`/api/data_matrix?freq=f1|f3|f7` 从 pickle 读取因子值返回矩阵

周线模式下：
- 日期列为周线 CSV 中的实际日期（含假期缩短周，如周四 6/18）
- 数据从 `CACHE["all_weekly"]` 读取，不存在时从日线 `rebuild_weekly_from_daily()` 生成
- 成交量/成交额切换使用颜色渐变（蓝色/紫色），按值域归一化

## 操作按钮语义

| 按钮 | 日线模式 | 周线模式 |
|------|---------|---------|
| **强制更新** | 删区间→API 拉取（覆盖式） | 从日线全量重建周线 |
| **补全空缺** | 检测日线缺口→增量拉取 | 检测周线缺口→从日线重建 |
| **删除选中** | 删除 CSV 行→重建周线 | 同（删日线→重建周线） |

## API 调用策略（关键）

**Tencent 财经 API**（`quant_data_fetcher.py:_tx_request`）：
```
GET ?param={code},{period},,{end_date},{count},qfq
```
- ❌ **不支持多 ETF 批量**：一次请求一个 code
- ❌ **不支持日期区间**：只接受 count（返回最近 N 行），start/end 由客户端过滤
- ✅ 盘后 Sina 快径支持单日批量追加（~2s 全 ETF）

## 拆股检测与修复（调用链路）

### 数据源

`_SPLIT_EVENTS` — 模块级 dict，code → [{action, ex_date, ratio}]

填充路径：
1. `_load_corporate_action_events()` — 读 `data/corporate_action_events.json`（已注册事件）
2. `detect_corporate_action_events()` — 调 AKShare `fund_cf_em` API（实时检测）
3. 合并去重，`_SPLIT_CHECKED` 标记保证只会调一次

### 比率来源

`ratio` 来自 AKShare API 返回的拆分比例，**不是从价格算出来的**。价格只用于判断"数据是否已修复"。

### 状态判定

`GET /api/split_status` 被调用时：
1. 调 `_ensure_splits_detected(cfg)` 保障事件已加载
2. 遍历 `_SPLIT_EVENTS`，查每支 ETF 最近一次拆股
3. 扫描 CSV（CACHE）最近 10 行 close → 有 >30% 跳变 → `pending_repair`；无 → `repaired`

### 触发时机

| 触发点 | 何时 | 作用 |
|--------|------|------|
| `preload()` 启动 | Tuner 启动时 | 调 `_load_corporate_action_events()` 加载已注册事件 |
| `refresh_data()` | 每次全量刷新 | 调 `_ensure_splits_detected()`（首次）+ `_apply_split_memory_bridge()`（内存清洗）|
| `dmLoadSplitStatus()` | DM 面板打开 | `GET /api/split_status` → 显示 ⚠ 标记 |
| `dmLoadMatrix()` 成功回调 | 数据加载完成 | 再次调 `dmLoadSplitStatus()` 确保 ⚠ 渲染 |

### 修复链路

⚠ 点击 → `dmShowSplitActions` → 弹窗 → 点击"修复拆股数据(1:N)" → `dmFullRefetchCode` → `POST /api/data_full_refetch(verify_split=true)` → `_SPLIT_EVENTS` 查比例 → `df.loc / ratio` 写入 CSV → 重建周线 → 重建因子缓存 → 验证连续性 → 清除标记

**强制更新的实际流程**：
1. 从 CSV 删除 `[start, end]` 区间
2. 调 `update_single(full=False, end_date=end)`
3. `fetch_etf_kline(start_date=新末笔日期)` → need_count = max(20, gap_days*2)
4. Tencent API 返回 ~20 行，客户端过滤 > start_date，追加到 CSV
5. 逐 ETF 循环，每次间隔 1s 防限流

**不会全量拉取**：增量模式下每次最多 ~20 行，与选中区间大小无关。详见 `plans/BUG-042.md`。

## 后端 API

| 端点 | 方法 | 参数 | 输出 | 备注 |
|------|------|------|------|------|
| `/api/data_matrix` | GET | start, end, freq, field | etfs[], dates[], cells{}, summary{} | freq=weekly 时日期来自周线 CSV |
| `/api/data_delete` | POST | operations[{code,start,end}] | {ok, deleted, errors} | 连续区间删除，自动重建周线 |
| `/api/data_refetch` | POST | operations[{code,start,end}], freq | {ok, results} | freq=weekly 时从日线重建周线，不联网 |
| `/api/data_fill_gaps` | POST | {codes, start, end, freq} | {ok, filled, perEtf} | freq=weekly 时检测周线缺口，从日线补建 |

基准指数（000300/000016/000905/399006）特殊处理：
- `data_matrix`：每次从磁盘重读，不走 CACHE 缓存
- `_reload_csv_to_cache`：也重载基准 daily + weekly CSV
- `data_refetch`/`data_fill_gaps`：构造最小 etf_entry 传 `update_single()`

## 回测引擎 NaN 防护（BUG-043）

`quant_backtest.py` 仓位离散化逻辑中，`target_positions.idxmax()` 在 Series 全零时返回 NaN，随后 `target_positions[nan]` 触发 `KeyError`。

### 触发条件

极端参数（高 `c_sensitivity` + 高 `concentration`）→ `effective_c` 过大 → softmax 权重极端集中 → 离散化后全仓归零。

### 计算链

```
c_sensitivity(UI ÷10) × concentration(UI ÷10) → effective_c
softmax(z_scores × effective_c) → 极端峰值
disc_step 离散化 → clip 为 0 → target_positions 全零
idxmax() → NaN → target_positions[nan] → KeyError
```

### 修复

`idxmax()` 结果使用前检查 `pd.isna(max_idx)`，为 NaN 时跳过 leftover 分配。修复位置：`quant_backtest.py:997,1002`。
