# ETF 池变更流程

> **触发词**: 用户说"换池"。AI 自动：检查数据 → 展示池状态 → 逐支执行 → 更新追踪文档。禁止批量改 config。

从筛选候选到落地归档的完整操作流程。

**关联文档**: 量化运维 → `docs/runbook/v2-quant/overview.md` | 筛选脚本 → `scripts/scan_etf_universe.py` | 池历史档案 → `research/pool/README.md`

## 流程总览

```
筛选                     决策                      执行                    收口
─────                    ────                      ────                    ────
scan_etf_universe.py     → 审阅候选 → 确认清单     → 逐支执行(本文 SOP)     → 更新 research/pool/
  --debug                → 大换池(5+)开REQ追踪      → 基线链验证             → 更新 research/pool/
                         → 小换池直接执行           → 失败不阻塞            
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

4. 清理数据：删除 `data/quant/{code}_daily.csv` + `{code}_weekly.csv`（孤儿文件；`pool_change.py --remove/--replace` 已自动处理）

5. python scripts/quant_backtest.py --preset gam-1 --start 2023-01-01 --end <latest>
   → 对比基线：EXIT=0，TR/Sharpe <±5%，MDD 不恶化

6. 通过 → 更新基线 → 登记 ✅ → 继续
   失败 → 回退 config → 登记 ❌ + 实际vs基线数字 → 继续下一支
```

## 替换流程

同"移除旧 → 新增新"，各跑一次基线。

## 配套同步清单（换池必查）

`config/quant_universe.yaml` 之外还有多处硬编码引用。换池（增/删/替）后**逐项检查**，遗漏会导致健康检查失真、推断日期过期、孤儿残留：

| 位置 | 改什么 | 说明 |
|------|--------|------|
| `config/config.yaml` → `system_check.etf_codes` | 删/换已下架 code | 完整性检查采样名单（硬编码） |
| `config/config.yaml` → `etfs` | 删下架 ETF 条目 | tracking_index / benchmark 配置 |
| `scripts/health_check.py` → `DEFAULT_ETF_CODES` | 同步 | config 缺失时的兜底，与上一条保持同一份名单 |
| `scripts/verify_html_integrity.py` → `DEFAULT_ETF_CODES` | 同步 | 同上 |
| `scripts/update_report.py` → `sample_csv` | 用 `510300_daily.csv`（沪深300基准），**勿引用池内 ETF** | 推断数据最新日期；基准永不因换池失效 |
| `data/quant/{code}_daily.csv` + `_weekly.csv` | 删除孤儿 | 手动改 config 绕过 `pool_change.py` 时不会自动清理 |
| `config/holdings.yaml` | 删下架 ETF 条目 + 更新顶部支数 | 成分股静态配置（REQ-107） |
| `config/valuation_anchors.yaml` | 删下架 ETF 锚点块 | 估值锚点 |
| `data/editorial_content.yaml` | 删下架 ETF 卡片 | 编辑内容 |
| `research/pool/rounds/` | 登记本轮 round（R N） | 换池历史证据 |

> **教训**（2026-10-31 实录）：上述 10 处配套引用被漏改，根因是换池只盯着 `quant_universe.yaml`。特别注意 **「核心观察名单」**（`system_check.etf_codes` + `etfs` + `holdings.yaml` + 两个脚本的 `DEFAULT_ETF_CODES`）是同一套 6 支 code，散落 5 处，必须**一处改动、五处同步**。`pool_change.py --remove/--replace` 会自动清理孤儿数据，但**手动编辑 config 时必须对照本清单逐项收口**。

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
```

## 关键约束

- 绝不批量拉取 — 每支独立验证
- 数据拉取: `scripts/quant_data_fetcher.py`（非 fetch_etf_kline.py）
- 回测参数: `--start/--end`（非 --window）
- 短名审核：去公司后缀，与池内风格一致，避免重名
- 期货/商品 ETF 短名前加「期货」二字（如 有色期货ETF、能源化工期货ETF、豆粕期货ETF），与股票 ETF 区分；黄金 ETF（518880 现货）不加

## 剔除备忘（默认不自动生成）

> **触发词**: 用户说「记录剔除 XXX」/「为什么删了 XXX」。AI 生成剔除备忘 → `research/pool/removals/{code}_{日期}.md`。

**只在用户需要时触发**，筛选流跑完不自动生成（只在控制台打印轻量「未入选 N 支」）。

备忘模板（实例见 `research/pool/removals/512400_2026-10-31.md`）：

- 标的信息（code/name/sector + 为什么重要）
- **贡献信息**（基准策略 gam-0 回测：选中率 / 均权重 / 笔数 / 胜率 / 赔率 / 交易盈亏）
- 剔除原因（环节 / 指标 / 排名）
- 撞车对象（表）
- 数据快照
- 决策与思考

贡献指标用 `quant_backtest.run_backtest(preset="gam-0", ...)` 的 `trade_log` + `signal_history` 计算，口径见 `docs/design/etf-contribution.md`。
