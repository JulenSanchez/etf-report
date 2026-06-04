# 2026-05-28 研究归档

> 本轮全部实验结论汇总。原始数据在 temp_scripts/ 和后台任务输出中，可复现。

## 1. 凯利 Bootstrap（REQ-250）

**结论**: 三派毁灭概率均为 0%。精算师历史 Geo 衰减仅 0.2pp（最稳），赌徒 Geo 波动 11.63%。
**脚本**: temp_scripts/kelly_bootstrap_20260528.py
**归档**: research/strategy/kelly/results.json

## 2. 多周期稳健性（REQ-222）

**结论**: 三派在三个 2Y 子周期均无亏损。P2(2022-2024 震荡市)是共同软肋。CV 最稳的是精算师(0.71)。
**脚本**: temp_scripts/multi_period_robustness_20260528.py
**归档**: research/strategy/robustness/results.json

## 3. 因子归因（REQ-233）

**结论**: 精算师 F7 区分力 39.2（5×高于其他人）。禅修者与赌徒因子剖面几乎相同(F1=8.0/8.0, F7=3.9/3.9)。ETF 重叠 78%。
**脚本**: temp_scripts/factor_attribution_20260528.py

## 4. 多窗口基线

**结论**: 三派 1Y/3Y/6Y 全量指标对比表。精算师 6Y AR=+49.2% 碾压，1Y AR=+118.8% 垫底。
**归档**: research/strategy/persona-baseline-20260528.md
**脚本**: temp_scripts/multi_window_baseline_20260528.py

## 5. 赌徒 TPE v2+v3（REQ-258）

**v2** (TR 目标): w=45/42/13, C=1.20, CS=14.3 → 等权 TR=+799.8%，6Y MDD=-20.2%(略超)
**v3** (AR 等权目标): w=56/24/20, C=0.43, CS=6.0, f1s=4.7, f3s=6.2, f7t=13.8, f7k=3.2, f7w=34 → 等权 AR=+92.4%(+13.3pp vs 基线)
**v3 已落地 YAML**。
**脚本**: temp_scripts/persona_bayesian_opt_20260528.py, gambler_expanded_tpe_20260528.py

## 6. 精算师+禅修者 TPE（REQ-253）

**精算师**: TPE S×C=33.6(+8.4% vs 基线 31.0)。w=57/33/10, C=0.61, CS=7.7。**未落地**(实盘不可跟随)。
**禅修者**: TPE Sharpe=2.30(+12% vs 基线 2.05)。w=49/32/19, C=0.35, f1s=4.0, f3s=1.4, f7t=26.2, f7k=3.0, f7w=29。**已落地 YAML**。
**脚本**: temp_scripts/actuary_zen_expanded_tpe_20260528.py

## 7. 因子衰减分析（REQ-225）

**结论**: 无因子在系统性衰退。F7 在精算师中极端稳定(IC=0.98)。F3 是结构性问题(IC 低是因权重低)而非衰减问题。F1_daily 方案被数据否决。
**脚本**: temp_scripts/factor_decay_20260528.py

## 8. F2 最终审判 + F1_daily 验证

**相关性**: F1↔F2 = +0.85（几乎同一信号）
**偏相关**: F2 控制 F1/F3/F7 后 = -0.04（无独立信息）
**AB 替换测试**: F2+F3+F7 AR=+25.9% vs F1+F3+F7 AR=+48.6%（腰斩）
**F1_daily 测试**: AR=+33.8% vs 标准 F1 AR=+73.4%（惨败）

**判决**: F2 正式退役。理由：F2 = F1 + 噪声，噪声无预测力。F1 的"滞后"是 feature(平滑噪声)，不是 bug。当日收盘价已被 F3(量价)和 F7(波动率)充分捕捉。
**脚本**: temp_scripts/f2_analysis_20260528.py, f1_daily_test_20260528.py

## 9. 前端对齐验证

**CLI 与 Tuner 前端完全一致**。赌徒 1Y 总收益 +175.84%，Sharpe 3.72。C/CS 缩放 bug 修复生效。

## 10. 外部调研

晨星 Style Box(风格箱+漂移测量)、CFE(因子暴露变化=alpha)、Barra(四层收益归因)。方法论已融入 v4 路线图。
**归档**: plans/V4_ROADMAP.md

---

## 未归档的数据（可复现，暂不紧急）

| 数据 | 位置 |
|------|------|
| 邻域优化 3Y 全量对比(18 组合) | temp_scripts/persona_neighborhood_opt_20260528.py 输出 |
| 禅修者 max_single 分布(1454 天) | temp_scripts/check_max_single_20260528.py 输出 |
| 赌徒 CS grid 41 组 | research/strategy/dynamic-C/cs_grid_search.json ✅ |
