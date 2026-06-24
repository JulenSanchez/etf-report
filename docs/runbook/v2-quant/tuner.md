# Tuner 运维

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
| `POST /api/refresh_data` | 刷新数据：盘中只更新 intraday cache，盘后写 CSV |
| `GET /api/data_status` | 查看 CSV / intraday cache 状态 |

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
