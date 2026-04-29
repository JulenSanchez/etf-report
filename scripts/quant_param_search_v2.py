#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 1 v2: 粗撒点权重网格搜索（2 年窗口 + regime-aware F4）

设计：
  - 粗网格 step=20: [0, 20, 40, 60, 80]
  - 回测窗口：2 年 (2024-04-29 → 2026-04-24)
  - 其他参数固定（同 Phase 1 v1）
  - 输出 CSV + Markdown 报告

使用：
  1. 确保 Tuner 在跑：python scripts/quant_tuner.py
  2. 运行：python scripts/quant_param_search_v2.py
"""

import csv
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from itertools import product
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SKILL_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = SKILL_DIR / "data" / "param_search"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TUNER_URL = "http://localhost:5179/api/run"
REQUEST_TIMEOUT = 90

# Coarse grid: step=20
WEIGHT_VALUES = [0, 20, 40, 60, 80]
TARGET_SUM = 100


def gen_weight_combinations():
    combos = []
    for w1, w2, w3, w4 in product(WEIGHT_VALUES, repeat=4):
        if w1 + w2 + w3 + w4 == TARGET_SUM:
            combos.append((w1, w2, w3, w4))
    return combos


def build_params(w1, w2, w3, w4, start_date, end_date):
    return {
        "w1": w1, "w2": w2, "w3": w3, "w4": w4,
        "bias": 0,
        "conf_type": "quadratic",
        "dead_zone": 25, "full_zone": 65,
        "max_holdings": 6, "disc_step": 5,
        "ema_period": 20, "rsi_period": 14, "vol_window": 20,
        "f1_sensitivity": 8.0, "f3_sensitivity": 1.0, "f2_dead_zone": 1.5,
        "start_date": start_date,
        "end_date": end_date,
    }


def call_tuner(params, retries=2):
    body = json.dumps(params).encode("utf-8")
    req = urllib.request.Request(
        TUNER_URL, data=body,
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
    raise RuntimeError(f"Tuner failed ({retries+1}x): {last_err}")


def classify_styles(rows):
    if not rows:
        return rows

    def quantile(values, q):
        sv = sorted(values)
        idx = max(0, min(len(sv) - 1, int(len(sv) * q)))
        return sv[idx]

    annual_vals = [r["annualReturn"] for r in rows]
    sharpe_vals = [r["sharpe"] for r in rows]
    calmar_vals = [r["calmar"] for r in rows]

    annual_top25 = quantile(annual_vals, 0.75)
    sharpe_top25 = quantile(sharpe_vals, 0.75)
    calmar_top25 = quantile(calmar_vals, 0.75)

    for r in rows:
        styles = []
        if r["annualReturn"] >= annual_top25: styles.append("high_ret")
        if r["sharpe"] >= sharpe_top25: styles.append("high_sharpe")
        if r["calmar"] >= calmar_top25: styles.append("high_calmar")
        w1, w2, w3, w4 = r["w1"], r["w2"], r["w3"], r["w4"]
        if w1 + w3 >= 60: styles.append("trend_vol")
        if w4 >= 40: styles.append("value")
        if w2 >= 20: styles.append("anomaly")
        if w4 == 0: styles.append("no_f4")
        r["styles"] = "|".join(styles) if styles else "neutral"
    return rows


def main():
    start_date = "2024-04-29"
    end_date = "2026-04-24"

    combos = gen_weight_combinations()
    print(f"Coarse grid search (step=20, 2yr window):")
    print(f"  Combos: {len(combos)}")
    print(f"  Window: {start_date} -> {end_date}")
    print()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = OUT_DIR / f"grid_coarse2y_{timestamp}.csv"
    md_path = OUT_DIR / f"grid_coarse2y_{timestamp}.md"

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
                "totalReturn": s.get("totalReturn", 0),
                "annualReturn": s.get("annualReturn", 0),
                "maxDrawdown": s.get("maxDrawdown", 0),
                "sharpe": s.get("sharpe", 0),
                "sortino": s.get("sortino", 0),
                "calmar": s.get("calmar", 0),
                "winRate": s.get("winRate", 0),
                "rebalanceCount": s.get("rebalanceCount", 0),
                "elapsed": s.get("elapsed", 0),
            }
            writer.writerow(row)
            f.flush()
            rows.append(row)

            if i % 5 == 0 or i == len(combos):
                pct = i / len(combos) * 100
                eta_sec = (time.time() - t_start) / i * (len(combos) - i)
                print(f"  [{i}/{len(combos)}] {pct:.1f}% ETA {eta_sec/60:.1f}m "
                      f"w=({w1},{w2},{w3},{w4}) ann={row['annualReturn']:.1f}% sh={row['sharpe']:.2f}")

    elapsed = time.time() - t_start
    print(f"\nDone: {len(rows)}/{len(combos)} in {elapsed/60:.1f} min")
    print(f"  CSV: {csv_path}")

    # Analysis
    classify_styles(rows)

    # Sort by annual return
    by_annual = sorted(rows, key=lambda r: r["annualReturn"], reverse=True)

    # Build report
    md = []
    md.append("# Phase 1 v2: Coarse Grid (2yr, step=20)")
    md.append("")
    md.append(f"- Window: {start_date} -> {end_date}")
    md.append(f"- Combos: {len(rows)}")
    md.append(f"- CSV: `{csv_path.name}`")
    md.append(f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    md.append("")
    md.append("Fixed: bias=0 / quadratic / dz=25 / fz=65 / hold=6 / step=5% / ema=20 / rsi=14 / vol=20 / f1s=8 / f3s=1.0 / f2dz=1.0")
    md.append("")
    md.append("---")
    md.append("")

    # Global stats
    annual_avg = sum(r["annualReturn"] for r in rows) / len(rows)
    sharpe_avg = sum(r["sharpe"] for r in rows) / len(rows)
    md.append("## Global Stats")
    md.append(f"- Avg annual: {annual_avg:.2f}%")
    md.append(f"- Avg Sharpe: {sharpe_avg:.2f}")
    md.append("")

    # F4=0 vs F4>0
    f4_zero = [r for r in rows if r["w4"] == 0]
    f4_nonzero = [r for r in rows if r["w4"] > 0]
    md.append("## F4=0 vs F4>0")
    if f4_zero:
        md.append(f"- F4=0 (n={len(f4_zero)}): avg annual {sum(r['annualReturn'] for r in f4_zero)/len(f4_zero):.2f}%, avg Sharpe {sum(r['sharpe'] for r in f4_zero)/len(f4_zero):.2f}")
    if f4_nonzero:
        md.append(f"- F4>0 (n={len(f4_nonzero)}): avg annual {sum(r['annualReturn'] for r in f4_nonzero)/len(f4_nonzero):.2f}%, avg Sharpe {sum(r['sharpe'] for r in f4_nonzero)/len(f4_nonzero):.2f}")
    md.append("")

    # Trend vs Value
    trend_rows = [r for r in rows if r["w1"] + r["w3"] >= 50]
    value_rows = [r for r in rows if r["w4"] >= 30]
    md.append("## Trend vs Value")
    if trend_rows:
        md.append(f"- Trend (w1+w3>=50, n={len(trend_rows)}): avg annual {sum(r['annualReturn'] for r in trend_rows)/len(trend_rows):.2f}%, Sharpe {sum(r['sharpe'] for r in trend_rows)/len(trend_rows):.2f}")
    if value_rows:
        md.append(f"- Value (w4>=30, n={len(value_rows)}): avg annual {sum(r['annualReturn'] for r in value_rows)/len(value_rows):.2f}%, Sharpe {sum(r['sharpe'] for r in value_rows)/len(value_rows):.2f}")
    md.append("")
    md.append("---")
    md.append("")

    # Top 10 by annual
    md.append("## Top 10 by Annual")
    md.append("")
    md.append("| # | w1 | w2 | w3 | w4 | Annual | Sharpe | Calmar | MDD | Styles |")
    md.append("|---|----|----|----|----|--------|--------|--------|-----|--------|")
    for i, r in enumerate(by_annual[:10], 1):
        md.append(f"| {i} | {r['w1']} | {r['w2']} | {r['w3']} | {r['w4']} | {r['annualReturn']:.2f}% | {r['sharpe']:.2f} | {r['calmar']:.2f} | {r['maxDrawdown']:.2f}% | {r['styles']} |")
    md.append("")

    # Top 10 by Sharpe
    by_sharpe = sorted(rows, key=lambda r: r["sharpe"], reverse=True)
    md.append("## Top 10 by Sharpe")
    md.append("")
    md.append("| # | w1 | w2 | w3 | w4 | Annual | Sharpe | Calmar | MDD | Styles |")
    md.append("|---|----|----|----|----|--------|--------|--------|-----|--------|")
    for i, r in enumerate(by_sharpe[:10], 1):
        md.append(f"| {i} | {r['w1']} | {r['w2']} | {r['w3']} | {r['w4']} | {r['annualReturn']:.2f}% | {r['sharpe']:.2f} | {r['calmar']:.2f} | {r['maxDrawdown']:.2f}% | {r['styles']} |")
    md.append("")

    # Bottom 5
    md.append("## Bottom 5")
    md.append("")
    md.append("| # | w1 | w2 | w3 | w4 | Annual | Sharpe | MDD | Styles |")
    md.append("|---|----|----|----|----|--------|--------|-----|--------|")
    for i, r in enumerate(by_annual[-5:], 1):
        md.append(f"| {i} | {r['w1']} | {r['w2']} | {r['w3']} | {r['w4']} | {r['annualReturn']:.2f}% | {r['sharpe']:.2f} | {r['maxDrawdown']:.2f}% | {r['styles']} |")
    md.append("")

    # F4 contribution analysis: group by w4 value
    md.append("## F4 Weight Impact (grouped by w4)")
    md.append("")
    md.append("| w4 | n | Avg Annual | Avg Sharpe | Avg Calmar |")
    md.append("|----|---|------------|------------|------------|")
    for w4_val in sorted(set(r["w4"] for r in rows)):
        group = [r for r in rows if r["w4"] == w4_val]
        aa = sum(r["annualReturn"] for r in group) / len(group)
        sa = sum(r["sharpe"] for r in group) / len(group)
        ca = sum(r["calmar"] for r in group) / len(group)
        md.append(f"| {w4_val} | {len(group)} | {aa:.2f}% | {sa:.2f} | {ca:.2f} |")
    md.append("")

    # F1 contribution analysis
    md.append("## F1 Weight Impact (grouped by w1)")
    md.append("")
    md.append("| w1 | n | Avg Annual | Avg Sharpe | Avg Calmar |")
    md.append("|----|---|------------|------------|------------|")
    for w1_val in sorted(set(r["w1"] for r in rows)):
        group = [r for r in rows if r["w1"] == w1_val]
        aa = sum(r["annualReturn"] for r in group) / len(group)
        sa = sum(r["sharpe"] for r in group) / len(group)
        ca = sum(r["calmar"] for r in group) / len(group)
        md.append(f"| {w1_val} | {len(group)} | {aa:.2f}% | {sa:.2f} | {ca:.2f} |")
    md.append("")

    md_path.write_text("\n".join(md), encoding="utf-8")
    print(f"  Report: {md_path}")

    # Console summary
    print("\n=== Top 5 by Annual ===")
    for i, r in enumerate(by_annual[:5], 1):
        print(f"  #{i} w=({r['w1']},{r['w2']},{r['w3']},{r['w4']}) "
              f"ann={r['annualReturn']:.2f}% sh={r['sharpe']:.2f} cal={r['calmar']:.2f} mdd={r['maxDrawdown']:.2f}%")

    print("\n=== F4 Impact ===")
    for w4_val in sorted(set(r["w4"] for r in rows)):
        group = [r for r in rows if r["w4"] == w4_val]
        aa = sum(r["annualReturn"] for r in group) / len(group)
        print(f"  w4={w4_val:3d} (n={len(group):2d}): avg_ann={aa:.2f}%")


if __name__ == "__main__":
    main()
