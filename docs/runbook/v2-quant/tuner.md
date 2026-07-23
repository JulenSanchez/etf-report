# Tuner 运维

> **触发词**: `启动 Tuner` `Tuner 白屏` `Tuner 报错` `Tuner 端口占用`

Tuner 是本地 Flask 调参和回测服务，默认地址 `http://localhost:5179`。

## 启动

```bash
python scripts/quant_tuner.py
# 或
python scripts/quant_lab/quant_tuner.py
```

如果只读预览，优先使用 readonly 模式（若当前脚本支持）：

```bash
python scripts/quant_tuner.py --readonly
```

## 主要 API

| API | 用途 |
|---|---|
| `GET /api/presets` | 返回 YAML preset 经 `quant_contract.py` 转换后的 Tuner 参数 |
| `POST /api/run` | 按参数运行回测 |
| `POST /api/save` | 将当前参数保存回 `config/quant_universe.yaml` |
| `POST /api/refresh_data` | 刷新数据：盘中更新 intraday cache，盘后写 CSV |
| `GET /api/data_status` | 查看 CSV / intraday cache 状态 |
| `GET /api/split_status` | 返回各 ETF 拆股状态（含 ⚠ 标记），DM 面板加载时调用 |
| `POST /api/data_full_refetch` | 全量重拉 + 拆股修复（`verify_split=true` 时除以 ratio 写 CSV） |

### 盘中回测（标准口径）

用户说"盘中回测"/"今天的数据"/"跑一下今天"时，AI 固定使用以下参数：

```
preset: gam-0
start_date: 当年 5 月 1 日（如 2026-05-01）
end_date: 当天
```

**操作顺序**：
1. `POST /api/refresh_data` — 先拉盘中数据
2. `POST /api/run`（勾选 debug）— 再跑回测
3. 跑完后读 `data/quant/debug_tuner.json` — 后续排查直接读这个文件

**为什么是 5 月 1 日**：覆盖最近 2~3 个月行情，够看趋势又不冗余。不要跑 1Y 或 6Y——用户要的是"最近发生了什么"。

### refresh_data 流程（v3.13.0, BUG-059 修复后）

```
refresh_data()
  → 拉取数据（增量 / Sina fast path / 补全空缺）
  → _reload_csv_to_cache
  → _ensure_splits_detected()    ← AKShare 检测拆股事件（首次调用，后续缓存）
  → _apply_split_memory_bridge() ← 内存清洗（盘中有 intraday cache 时亦生效，自愈：已调整则跳过）
  → if post_market:
       _full_refetch_split_etfs() ← 全量重拉拆股 ETF（qfq 调整后永久修 CSV）
       _reload_csv_to_cache
  → precompute → 回测消费
```

> **注意**：盘中 `refresh_data` 仍会做 AKShare 事件加载 + 内存桥接（保证回测数据连续），
> 但不再做 DM 面板的 pending 检测——该检测收敛到 `/api/split_status`（DM 面板加载时触发）。
> 盘中拉取的数据（intraday cache）不落 CSV。

### 拆股修复用户流程（REQ-360 + BUG-059）

```
用户盘中拉数据
  → 打开"数据管理"面板
  → GET /api/split_status 自动检测：
      1. AKShare 确认该 ETF 有拆股事件
      2. CSV 末笔收盘价 ÷ 盘中实时价 ≈ 拆分比例 → 标记 pending_repair
  → ETF 行左侧出现 ⚠ 三角感叹号
  → 用户点 ⚠ → 弹出"修复拆股数据 (1:N)"按钮
  → 确认 → POST /api/data_full_refetch {verify_split: true}
        → CSV 中 ex_date 之前的 open/close/high/low 全部 ÷ N
        → 验证无残留跳变
        → 清除因子缓存 + 重建
        → 重载 CSV 到 CACHE
        → ⚠ 消失
```

**设计原则**：
- 盘中**只检测不修复**——让用户在 DM 面板看到原始跳变（红色异常格），才有动机点修复
- 修复入口收敛到 DM 面板 `/api/split_status`，不管数据从哪个入口拉的，打开 DM 就能看到
- 修复后自动清除因子缓存并重建，确保回测结果正确

## 参数契约

事实源：`src/etf_report/core/quant_contract.py`。

```text
config/quant_universe.yaml preset
  → preset_to_tuner_params()
  → /api/presets
  → Tuner UI
  → /api/run
  → tuner_params_to_config_override()
  → run_backtest(config_override=...)
```

改参数时必须同步：

- `src/etf_report/core/quant_contract.py`
- `templates/tuner.html`
- `tests/test_quant_contract.py`
- `config/quant_universe.yaml`（如默认值变化）

## 前端控件 → API 映射速查

| 控件 | 触发 API | 产出 / 关键参数 | 详细设计 |
|------|---------|----------------|---------|
| Run Backtest 按钮 | `POST /api/run?async=1` | 回测结果 | `tuner-ui.md` §5.3 |
| Refresh 按钮 | `POST /api/refresh_data` | intraday cache + CSV | `tuner-ui.md` §5.3 |
| Save YAML 按钮 | `POST /api/save` | 写入 `quant_universe.yaml` | `tuner-ui.md` §5.3 |
| debug pill | `POST /api/run`（带 `debug=true`） | `data/quant/debug_tuner.json` | `tuner-ui.md` §5.3 + `backtest-engine.md` §8.4 |
| 数据新鲜度 badge | `GET /api/data_status` | confirmed/intraday/stale | `tuner-ui.md` §5.3 |
| 热力图 | `GET /api/heatmap_data?lookback=N` | heatmap JSON | `tuner-ui.md` §5.6 |
| 前沿点选择器 | `GET /api/frontier` | frontier JSON | `tuner-ui.md` §5.8 |
| 进度条 | （回测进度回调） | 实时 % | `tuner-ui.md` §5.5 |
| 4 个 view tab | （前端切换） | guide/results/heatmap/datamgmt | `tuner-ui.md` §5.11 |
| 数据管理视图 | （独立 API） | 详见 `data-management-panel.md` | `tuner-ui.md` §5.12 |

**排障提示**：控件行为异常时，先查对应 API 的后端日志，再查 `tuner-ui.md` §5 的交互行为定义。debug pill 产出的 `debug_tuner.json` 是排查信号不一致的首选工具（字段结构见 `backtest-engine.md` §8.4）。

## 常见故障

| 症状 | 处理 |
|---|---|
| 页面白屏 | 打开浏览器控制台；优先查 preset 字段是否缺失，特别是右侧卡片依赖字段 |
| `/api/presets` 报错 | 先跑 `python -m pytest tests/test_quant_contract.py -q` |
| `/api/run` 返回权重错误 | 检查 `w1+w3+w7 == 100`，以及 `quant_contract.preset_to_tuner_params()` 转换逻辑 |
| 端口占用 | 运行 `python scripts/kill_tuner.py` 或关闭已有 Flask 进程 |
| 保存后参数异常 | 对比 `config/quant_universe.yaml`，确认 `tuner_params_to_preset_patch()` 未丢字段 |

## 最小验证

```bash
python -m pytest tests/test_quant_contract.py -q
python -m pytest tests/test_quant_consistency.py -q
```

## 配色系统维护

Tuner 所有语义色通过两级集中定义管理，**改主题色只需改这两处**：

### 事实源

| 层级 | 位置 | 格式 |
|------|------|------|
| CSS | `templates/tuner.html` → `<style>` 顶部 `:root { ... }` 块 | `--name: #hex;` |
| JS | `templates/tuner.html` → `<script>` 顶部 `var TC = { ... };` | `name: '#hex',` |

设计文档：`docs/design/tuner-ui.md` §4。

### 改主题色

1. 改 `:root` 块中对应变量的色值
2. 改 `TC` 对象中对应 key 的色值（必须与 CSS 变量**同步**）
3. 刷新浏览器 → 生效（无需重启 Tuner）

### 加新颜色

1. `:root` 块末尾加 `--new-name: #xxx;`
2. `TC` 对象末尾加 `newName: '#xxx',`
3. CSS 中用 `var(--new-name)`，JS 中用 `TC.newName`

### 不改动区

以下色值**不需要也**不应该强行 var 化（原因见 `docs/design/tuner-ui.md` §4.4）：
- 热力图 diverging 色阶
- 涨跌分布 bin 色阶
- 数据新鲜度 badge 背景
- 扇区/Group1 色表（已是 JS 集中定义）
- 因子曲线色表（已是 JS 集中定义）
