# ETF 池变更流程

> **触发词**: 用户说"换池"。AI 自动：检查数据 → 展示池状态 → 逐支执行 → 更新追踪文档。禁止批量改 config。

从筛选候选到落地归档的完整操作流程。

**关联文档**: 量化运维 → `docs/runbook/v2-quant/overview.md` | 筛选脚本 → `scripts/scan_etf_universe.py` | 池历史档案 → `research/pool/README.md`

## 流程总览

```
筛选                     决策                      执行                    收口
─────                    ────                      ────                    ────
scan_etf_universe.py     → 审阅候选 → 确认清单     → 逐支执行(本文 SOP)     → 更新 research/pool/
  --debug                → 大换池(5+)开REQ追踪      → 基线链验证             → 生成待提交清单
                         → 小换池直接执行           → 失败不阻塞             → 发布按 release.md
```

| 换池规模 | 追踪方式 | 示例 |
|---------|---------|------|
| 大换池（5+ 支变更） | 开 `plans/REQ-XXX.md` 记录决策和基线链 | REQ-274 本轮 |
| 小换池（单支替换） | 直接在 `research/pool/README.md` 记 Applied | 替换一支德国 ETF |

两种规模均使用下文的执行 SOP。

## 新增流程

```
1. python scripts/quant_backtest.py --preset gam-1 --start 2023-01-01 --end <latest>
   → 记录 TR/Sharpe/MDD 作为变更前基线

2. python scripts/quant_data_fetcher.py --full --code <code>
   → 失败 → 跳过，登记原因

3. 检查 history_days ≥ 250（1年）
   → < 250 → 向用户预警，确认后继续

4. 审核扇区归属
   → 优先归入已有扇区（参考 Tuner `secPalette`：科技/TMT/新能源/医药/消费/金融/资源周期/传统/制造/另类）
   → 独苗扇区缺乏横向对比、无热力图配色，仅当 ETF 确实无法归入任何已有扇区时才新建
   → 新建扇区须同步更新 `templates/tuner.html` 的 `secPalette` 加配色
   > **AI 必须暂停**: 扇区归属需用户确认，AI 展示建议后等待确认再继续。

5. 更新 config/quant_universe.yaml
   → 含短名审核（去公司后缀，与池内风格一致，避免重名）
   > **AI 必须暂停**: 短名需用户确认，AI 展示建议后等待确认再继续。

6. python scripts/quant_backtest.py --preset gam-1 --start 2023-01-01 --end <latest>
   → 对比基线：EXIT=0，无 NaN，TR/Sharpe 无断崖下跌

7. 通过 → 更新基线 → 登记 ✅ → 继续下一支
   失败 → 回退 config → 登记 ❌ + 实际vs基线数字 → 继续下一支（不阻塞）
```

→ **AI 验证**: Step 1 应输出 TR/Sharpe/MDD 三行数字。Step 2 应输出 `OK [full] daily+N weekly+M`。Step 6 应输出 `EXIT=0` 且 TR/Sharpe/MDD 与基线对比在阈值内。

## 移除流程

```
1. python scripts/quant_backtest.py --preset gam-1 --start 2023-01-01 --end <latest>
   → 记录 TR/Sharpe/MDD 作为变更前基线

2. 检查行业覆盖：移除后同粗组是否有替代 ETF

3. 更新 config/quant_universe.yaml（删除条目）

4. python scripts/quant_backtest.py --preset gam-1 --start 2023-01-01 --end <latest>
   → 对比基线：EXIT=0，TR/Sharpe <±5%，MDD 不恶化

5. 通过 → 更新基线 → 登记 ✅ → 继续
   失败 → 回退 config → 登记 ❌ + 实际vs基线数字 → 继续下一支
```

## 替换流程

同"移除旧 → 新增新"，各跑一次基线。

## 接受标准

| 检查项 | 新增 | 移除 |
|--------|------|------|
| 数据量 | history_days ≥ 250 | — |
| 回测通过 | EXIT=0，无 NaN | EXIT=0，无 NaN |
| TR | 下降 < 500bps | 变化 < ±5% |
| Sharpe | 下降 < 0.20 | 变化 < ±5% |
| MDD | 不恶化 | 不恶化 |
| 行业覆盖 | 不造成过度集中 | 移除后仍有替代 ETF |

## 基线链

每次变更后更新基线，形成追踪链：

```
基线₀(变更前) → 基线₁(#1后) → 基线₂(#2后) → ... → 基线ₙ(#N后)
```

全部完成后汇总报告所有失败项及原因。

## 收口

```
1. 更新 research/pool/README.md
   → Applied 日志 + 证据链接；不要维护当前 universe 副本
2. 输出待提交清单
   → config / research / tests / docs 的变更范围
3. 发布或提交
   → 由用户显式触发，按 docs/runbook/release.md 执行
4. stable 同步
   → 发布后如需更新计划任务仓，按 docs/runbook/stable.md 执行
```

## 关键约束

- 绝不批量拉取 — 每支独立验证
- 数据拉取: `scripts/quant_data_fetcher.py`（非 fetch_etf_kline.py）
- 回测参数: `--start/--end`（非 --window）
- 短名审核：去公司后缀，与池内风格一致，避免重名
