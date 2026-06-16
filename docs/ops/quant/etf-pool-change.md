# ETF 池变更入口

ETF 池变更的唯一 SOP 入口是：

```text
docs/ops/pool-change.md
```

本文件仅作为量化运维目录下的跳转页，避免在多个文档中维护双份规则。

## 强制规则

- 任何新增、移除、替换 ETF 前，先读 `docs/ops/pool-change.md`。
- 禁止批量改 `config/quant_universe.yaml` 后只跑一次验证。
- 每支 ETF 独立执行：拉数、检查数据量、更新配置、回测、记录结果。
- 大换池（5 支以上）必须有 REQ 追踪；小换池至少记录到 `research/pool/README.md`。

## 相关文件

- 当前池事实源：`config/quant_universe.yaml`
- 筛选脚本：`scripts/scan_etf_universe.py`
- 池历史：`research/pool/README.md`
- 变更 SOP：`docs/ops/pool-change.md`
