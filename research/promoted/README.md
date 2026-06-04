# Promotion Log — 研究结论投产记录

> research → production 的移交闸门。每条记录包含：结论摘要、来源实验、对应 REQ、落地位置。

## 2026-05

| 日期 | 内容 | 来源 | 对应 REQ | 落地 |
|------|------|------|---------|------|
| 05-28 | 三大人设终局参数(精算师/禅修者/赌徒) | TPE v2/v3 | REQ-258/253 | `config/quant_universe.yaml` |
| 05-28 | 三周期等权统一(1Y/3Y/6Y各1/3) | 多窗口基线 | REQ-252 | 所有优化目标函数 |
| 05-28 | F4(估值)/F5(波动率)全量清退 | 因子归因+历史结论 | REQ-255 | UI/contract/YAML 移除 |
| 05-28 | 信心函数仅保留 MA 趋势 | 用户判断 | REQ-256 | Tuner UI 移除4按钮 |
| 05-28 | 凯利Bootstrap：三人毁灭概率0% | Bootstrap 2000路径 | REQ-250 | 归档 research/strategy/kelly/ |
| 05-28 | 因子归因：精算师F7驱动，禅修者/赌徒F1驱动 | 6Y信号分解 | REQ-233 | research/strategy/ 归档 |
| 05-28 | C/CS 缩放 bug 修复 | Tuner 对比测试 | REQ-252 | `quant_contract.py` + `tuner.html` |
| 05-28 | Tuner F3灵敏度 max→8.0 + 集中度 step→0.01 | 赌徒参数需求 | REQ-259 | `tuner.html` |
| 05-29 | 精算师30维子参数落地(S×C 41.6→46.6) | sub-TPE | REQ-253 | `quant_universe.yaml` |
| 05-29 | 赌徒30维过拟合→还原至已验证版本 | TPE验证失败 | — | `quant_universe.yaml` |
| 05-29 | 禅修者子参数无提升，确认局部最优 | sub-TPE | — | 不改 |
| 05-29 | 流派分组UI + score_band浮点支持 | — | REQ-259 | `tuner.html` |
| 05-29 | v3.3.0封版，v4基线就绪 | — | — | `plans/Board.md` |
