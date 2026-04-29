#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REQ-183 Phase 1: 量化策略权重网格搜索

设计：
  - 通过 HTTP 调用 Tuner 的 /api/run，复用其内存缓存（不用重新 preload）
  - 网格搜索 F1~F4 权重（step=10%），bias_bonus 固定 0
  - 其他参数固定（用 momentum preset 默认值）
  - 回测窗口：近 1 年（自动算成 start_date / end_date）
  - 输出：CSV (每行一组合) + Markdown 报告（Top 5 风格代表）

使用：
  1. 先确保 Tuner 在跑：python scripts/quant_tuner.py
  2. 运行：python scripts/quant_param_search.py
  3. 结果：data/param_search/grid_w1234_<yyyymmdd_hhmmss>.csv
            + data/param_search/top5_styles_<yyyymmdd_hhmmss>.md
"""

import csv
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from itertools import product
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SKILL_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = SKILL_DIR / "data" / "param_search"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TUNER_URL = "http://localhost:5179/api/run"
REQUEST_TIMEOUT = 60  # seconds

# ============================================================
# Search space
# ============================================================
WEIGHT_VALUES = [0, 10, 20, 30, 40, 50, 60]  # 共 7 档
TARGET_SUM = 100  # 权重总和约束


def gen_weight_combinations():
    """生成所有满足 sum=100 的 (w1, w2, w3, w4) 组合。"""
    combos = []
    for w1, w2, w3, w4 in product(WEIGHT_VALUES, repeat=4):
        if w1 + w2 + w3 + w4 == TARGET_SUM:
            combos.append((w1, w2, w3, w4))
    return combos


# ============================================================
# Fixed (non-searched) params, mirrors momentum preset defaults
# ============================================================
def build_params(w1, w2, w3, w4, start_date, end_date):
    return {
        "w1": w1, "w2": w2, "w3": w3, "w4": w4,
        "bias": 0,                # Phase 1 固定 bias=0
        "conf_type": "quadratic",
        "dead_zone": 25,          # 信心函数死区，留到 Phase 2 扫
        "full_zone": 65,
        "max_holdings": 6,
        "disc_step": 5,
        "ema_period": 20,
        "rsi_period": 14,
        "vol_window": 20,
        "f1_sensitivity": 8.0,
        "f3_sensitivity": 1.0,
        "f2_dead_zone": 1.0,
        "start_date": start_date,
        "end_date": end_date,
    }


# ============================================================
# Tuner API call
# ============================================================
def call_tuner(params, retries=2):
    body = json.dumps(params).encode("utf-8")
    req = urllib.request.Request(
        TUNER_URL,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    last_err = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            time.sleep(1)
    raise RuntimeError(f"Tuner 调用失败 ({retries+1} 次): {last_err}")


# ============================================================
# Style labeling (规则分类，先简单粗暴)
# ============================================================
def classify_styles(rows):
    """对 rows (list of dict) 按多维度 Top/Bottom 25% 标签。

    返回 rows（in-place 添加 'styles' 字段，是 list[str]）
    """
    if not rows:
        return rows

    def quantile(values, q):
        sv = sorted(values)
        idx = int(len(sv) * q)
        idx = max(0, min(len(sv) - 1, idx))
        return sv[idx]

    annual_vals  = [r["annualReturn"] for r in rows]
    sharpe_vals  = [r["sharpe"]       for r in rows]
    calmar_vals  = [r["calmar"]       for r in rows]
    mdd_vals     = [r["maxDrawdown"]  for r in rows]   # 越小越好（负值）
    rebal_vals   = [r["rebalanceCount"] for r in rows]

    annual_top25 = quantile(annual_vals, 0.75)
    sharpe_top25 = quantile(sharpe_vals, 0.75)
    calmar_top25 = quantile(calmar_vals, 0.75)
    mdd_bot25    = quantile(mdd_vals, 0.25)            # 回撤更小（更负-接近0那一头）→ 取 25 分位的"上方"
    rebal_bot25  = quantile(rebal_vals, 0.25)

    # 趋势 / 价值 倾向标签 (E 假设的验证)
    for r in rows:
        styles = []
        if r["annualReturn"]   >= annual_top25: styles.append("高收益")
        if r["sharpe"]         >= sharpe_top25: styles.append("高Sharpe")
        if r["calmar"]         >= calmar_top25: styles.append("高Calmar")
        if r["maxDrawdown"]    >= mdd_bot25:    styles.append("低回撤")  # 回撤是负数，>= 25 分位 = 更接近 0
        if r["rebalanceCount"] <= rebal_bot25:  styles.append("低换手")

        # 趋势 vs 价值 vs 量能 vs 异动 取向（基于权重）
        w1, w2, w3, w4 = r["w1"], r["w2"], r["w3"], r["w4"]
        trend_w   = w1
        value_w   = w4
        volume_w  = w3
        rsi_w     = w2
        if trend_w  + volume_w >= 60:  styles.append("趋势量能型")
        if value_w  >= 40:             styles.append("价值型")
        if rsi_w    >= 30:             styles.append("异动型")
        if w4 == 0:                    styles.append("无估值")

        r["styles"] = "|".join(styles) if styles else "中性"
    return rows


# ============================================================
# Top-N selector (per-style)
# ============================================================
STYLE_KEYS = ["高收益", "高Sharpe", "高Calmar", "低回撤", "低换手"]

def pick_top_per_style(rows):
    """对每个风格类别选出最优代表（按对应排序键）。"""
    sort_keys = {
        "高收益":   ("annualReturn",   True),
        "高Sharpe": ("sharpe",         True),
        "高Calmar": ("calmar",         True),
        "低回撤":   ("maxDrawdown",    True),  # maxDrawdown 是负数，True=最大→最接近0
        "低换手":   ("rebalanceCount", False),
    }
    picks = {}
    for style, (key, desc) in sort_keys.items():
        sorted_rows = sorted(rows, key=lambda r: r[key], reverse=desc)
        picks[style] = sorted_rows[0] if sorted_rows else None
    return picks


# ============================================================
# Markdown report
# ============================================================
def build_markdown_report(rows, picks, start_date, end_date, csv_path):
    """生成 Top 风格报告 + 整体统计。"""
    md = []
    md.append("# Phase 1 权重网格搜索结果")
    md.append("")
    md.append(f"- **回测窗口**：{start_date} → {end_date}")
    md.append(f"- **总组合数**：{len(rows)}")
    md.append(f"- **CSV 详细数据**：`{csv_path.name}`")
    md.append(f"- **生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    md.append("")
    md.append("固定参数：bias=0 / conf=quadratic / dead_zone=25 / full_zone=65 / max_holdings=6 / step=5%")
    md.append("/ ema=20w / rsi=14d / vol_window=20 / f1_sens=8 / f3_sens=1.0 / f2_dz=1.0")
    md.append("")
    md.append("---")
    md.append("")

    # 全局统计
    md.append("## 整体统计")
    md.append("")
    annual_avg = sum(r["annualReturn"] for r in rows) / len(rows)
    sharpe_avg = sum(r["sharpe"] for r in rows) / len(rows)
    mdd_avg    = sum(r["maxDrawdown"] for r in rows) / len(rows)
    md.append(f"- 平均年化收益：{annual_avg:.2f}%")
    md.append(f"- 平均 Sharpe：{sharpe_avg:.2f}")
    md.append(f"- 平均最大回撤：{mdd_avg:.2f}%")
    md.append("")

    # E 假设 1：趋势 vs 价值
    md.append("### E.1 趋势 vs 价值假设验证")
    md.append("")
    trend_rows = [r for r in rows if r["w1"] + r["w3"] >= 50]
    value_rows = [r for r in rows if r["w4"] >= 30]
    if trend_rows:
        md.append(f"- **趋势型组合** (w1+w3 ≥ 50, n={len(trend_rows)})：")
        md.append(f"  平均年化 {sum(r['annualReturn'] for r in trend_rows)/len(trend_rows):.2f}% / 平均 Sharpe {sum(r['sharpe'] for r in trend_rows)/len(trend_rows):.2f}")
    if value_rows:
        md.append(f"- **价值型组合** (w4 ≥ 30, n={len(value_rows)})：")
        md.append(f"  平均年化 {sum(r['annualReturn'] for r in value_rows)/len(value_rows):.2f}% / 平均 Sharpe {sum(r['sharpe'] for r in value_rows)/len(value_rows):.2f}")
    md.append("")

    # E 假设：F4=0
    md.append("### F4=0 vs F4>0 对比")
    md.append("")
    f4_zero = [r for r in rows if r["w4"] == 0]
    f4_nonzero = [r for r in rows if r["w4"] > 0]
    if f4_zero:
        md.append(f"- **F4=0 组合** (n={len(f4_zero)})：平均年化 {sum(r['annualReturn'] for r in f4_zero)/len(f4_zero):.2f}% / Sharpe {sum(r['sharpe'] for r in f4_zero)/len(f4_zero):.2f}")
    if f4_nonzero:
        md.append(f"- **F4>0 组合** (n={len(f4_nonzero)})：平均年化 {sum(r['annualReturn'] for r in f4_nonzero)/len(f4_nonzero):.2f}% / Sharpe {sum(r['sharpe'] for r in f4_nonzero)/len(f4_nonzero):.2f}")
    md.append("")
    md.append("---")
    md.append("")

    # Top 5 各风格代表
    md.append("## Top 5 风格代表")
    md.append("")
    md.append("| 风格 | w1 | w2 | w3 | w4 | 总收益 | 年化 | Sharpe | Sortino | Calmar | MDD | 调仓数 |")
    md.append("|------|----|----|----|----|--------|------|--------|---------|--------|-----|--------|")
    for style, row in picks.items():
        if row is None: continue
        md.append(
            f"| **{style}** | {row['w1']} | {row['w2']} | {row['w3']} | {row['w4']} "
            f"| {row['totalReturn']:.2f}% | {row['annualReturn']:.2f}% | {row['sharpe']:.2f} "
            f"| {row['sortino']:.2f} | {row['calmar']:.2f} | {row['maxDrawdown']:.2f}% | {row['rebalanceCount']} |"
        )
    md.append("")

    # Top 10 by annual return
    md.append("## Top 10 by 年化收益")
    md.append("")
    md.append("| Rank | w1 | w2 | w3 | w4 | 年化 | Sharpe | Calmar | MDD | 风格标签 |")
    md.append("|------|----|----|----|----|------|--------|--------|-----|---------|")
    top10_annual = sorted(rows, key=lambda r: r["annualReturn"], reverse=True)[:10]
    for i, r in enumerate(top10_annual, 1):
        md.append(
            f"| #{i} | {r['w1']} | {r['w2']} | {r['w3']} | {r['w4']} "
            f"| {r['annualReturn']:.2f}% | {r['sharpe']:.2f} | {r['calmar']:.2f} | {r['maxDrawdown']:.2f}% | {r['styles']} |"
        )
    md.append("")

    # Top 10 by Sharpe
    md.append("## Top 10 by Sharpe")
    md.append("")
    md.append("| Rank | w1 | w2 | w3 | w4 | 年化 | Sharpe | Calmar | MDD | 风格标签 |")
    md.append("|------|----|----|----|----|------|--------|--------|-----|---------|")
    top10_sharpe = sorted(rows, key=lambda r: r["sharpe"], reverse=True)[:10]
    for i, r in enumerate(top10_sharpe, 1):
        md.append(
            f"| #{i} | {r['w1']} | {r['w2']} | {r['w3']} | {r['w4']} "
            f"| {r['annualReturn']:.2f}% | {r['sharpe']:.2f} | {r['calmar']:.2f} | {r['maxDrawdown']:.2f}% | {r['styles']} |"
        )
    md.append("")

    # Bottom 5 (反面教材)
    md.append("## Bottom 5 by 年化收益（反面教材，看哪些组合是雷）")
    md.append("")
    md.append("| Rank | w1 | w2 | w3 | w4 | 年化 | Sharpe | MDD | 风格标签 |")
    md.append("|------|----|----|----|----|------|--------|-----|---------|")
    bot5 = sorted(rows, key=lambda r: r["annualReturn"])[:5]
    for i, r in enumerate(bot5, 1):
        md.append(
            f"| #{i} | {r['w1']} | {r['w2']} | {r['w3']} | {r['w4']} "
            f"| {r['annualReturn']:.2f}% | {r['sharpe']:.2f} | {r['maxDrawdown']:.2f}% | {r['styles']} |"
        )
    md.append("")

    return "\n".join(md)


# ============================================================
# Main
# ============================================================
def main():
    # 计算回测窗口：近 1 年
    today = datetime.now().date()
    end_date = today.strftime("%Y-%m-%d")
    start_date = (today - timedelta(days=365)).strftime("%Y-%m-%d")

    combos = gen_weight_combinations()
    print(f"权重网格搜索：")
    print(f"  组合数：{len(combos)}")
    print(f"  回测窗口：{start_date} → {end_date}")
    print(f"  Tuner URL：{TUNER_URL}")
    print(f"  预计耗时：{len(combos) * 12 / 60:.1f} 分钟（每个组合 ~12s）")
    print()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = OUT_DIR / f"grid_w1234_{timestamp}.csv"
    md_path  = OUT_DIR / f"top5_styles_{timestamp}.md"

    # CSV header
    csv_fields = [
        "w1", "w2", "w3", "w4",
        "totalReturn", "annualReturn", "maxDrawdown",
        "sharpe", "sortino", "calmar", "winRate",
        "rebalanceCount", "elapsed",
    ]

    rows = []
    t_start = time.time()

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields)
        writer.writeheader()

        for i, (w1, w2, w3, w4) in enumerate(combos, 1):
            params = build_params(w1, w2, w3, w4, start_date, end_date)
            try:
                resp = call_tuner(params)
            except Exception as e:
                print(f"  [{i}/{len(combos)}] w=({w1},{w2},{w3},{w4}) FAIL: {e}")
                continue

            if "error" in resp and resp["error"]:
                print(f"  [{i}/{len(combos)}] w=({w1},{w2},{w3},{w4}) ERR: {resp['error']}")
                continue

            s = resp.get("summary", {})
            row = {
                "w1": w1, "w2": w2, "w3": w3, "w4": w4,
                "totalReturn":     s.get("totalReturn", 0),
                "annualReturn":    s.get("annualReturn", 0),
                "maxDrawdown":     s.get("maxDrawdown", 0),
                "sharpe":          s.get("sharpe", 0),
                "sortino":         s.get("sortino", 0),
                "calmar":          s.get("calmar", 0),
                "winRate":         s.get("winRate", 0),
                "rebalanceCount":  s.get("rebalanceCount", 0),
                "elapsed":         s.get("elapsed", 0),
            }
            writer.writerow(row)
            f.flush()  # 实时写盘，崩了能续
            rows.append(row)

            # 进度打印（每 10 个）
            if i % 10 == 0 or i == len(combos):
                pct = i / len(combos) * 100
                eta_sec = (time.time() - t_start) / i * (len(combos) - i)
                print(f"  [{i}/{len(combos)}] {pct:.1f}% · ETA {eta_sec/60:.1f} min · "
                      f"w=({w1},{w2},{w3},{w4}) annual={row['annualReturn']:.1f}% sharpe={row['sharpe']:.2f}")

    elapsed = time.time() - t_start
    print()
    print(f"✓ 完成 {len(rows)}/{len(combos)} 组合，总耗时 {elapsed/60:.1f} 分钟")
    print(f"  CSV: {csv_path}")

    # 风格分类 + Top picks
    classify_styles(rows)
    picks = pick_top_per_style(rows)

    # Markdown 报告
    md_content = build_markdown_report(rows, picks, start_date, end_date, csv_path)
    md_path.write_text(md_content, encoding="utf-8")
    print(f"  Report: {md_path}")
    print()
    print("=== Top 5 风格速览 ===")
    for style, row in picks.items():
        if row is None: continue
        print(f"  {style:>10}: w=({row['w1']},{row['w2']},{row['w3']},{row['w4']}) "
              f"annual={row['annualReturn']:.2f}% sharpe={row['sharpe']:.2f} "
              f"calmar={row['calmar']:.2f} mdd={row['maxDrawdown']:.2f}%")


if __name__ == "__main__":
    main()
