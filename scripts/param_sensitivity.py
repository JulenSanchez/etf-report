"""
REQ-190: 策略参数敏感性分析 — 单变量扫描脚本

用法：
  python scripts/param_sensitivity.py

前置：tuner 已在 localhost:5179 运行

输出：
  - 控制台打印敏感性表格
  - CSV 写入 data/req190_sensitivity.csv
"""

import json
import sys
import time
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SKILL_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

API_URL = "http://localhost:5179/api/run"

# weekly_trend baseline (3yr window)
BASELINE = {
    "w1": 40, "w2": 0, "w3": 60, "w4": 0,
    "bias": 0,
    "f1_sensitivity": 8.0,
    "f3_sensitivity": 1.0,
    "f2_dead_zone": 1.5,
    "conf_type": "ma_trend",
    "ma_bull_pos": 1.0,
    "ma_bear_pos": 0.4,
    "ma_trend_period": 20,
    "max_holdings": 6,
    "disc_step": 5,
    "rebalance_freq": "W-FRI",
    "score_band": 0,
    "ema_period": 16,
    "rsi_period": 14,
    "vol_window": 20,
    # 3yr window
    "start_date": "2023-05-01",
    "end_date": "2026-04-30",
}

# Parameters to sweep: (param_key, display_name, values)
SWEEPS = [
    ("ema_period",      "EMA周期",     [8, 12, 16, 20, 24, 28, 32, 36, 40]),
    ("ma_trend_period",  "MA趋势周期",  [10, 14, 18, 20, 22, 26, 30, 36, 40]),
    ("max_holdings",     "最大持仓",    [3, 4, 5, 6, 7, 8]),
    ("disc_step",        "离散化步长",  [5, 10, 15]),
    ("f1_sensitivity",   "F1 sigmoid", [3.0, 5.0, 8.0, 10.0, 12.0, 15.0]),
    ("f3_sensitivity",   "F3 指数尺度", [0.5, 0.7, 1.0, 1.5, 2.0, 2.5, 3.0]),
    ("vol_window",       "量比窗口",    [5, 10, 15, 20, 25, 30, 35, 40]),
    ("rsi_period",       "RSI周期",     [6, 10, 14, 18, 22, 28]),
    ("f2_dead_zone",     "F2死区半宽",  [0.3, 0.5, 1.0, 1.5, 2.0]),
    ("bias",             "偏好加成",    [0, 2, 4, 6, 8]),
]


def run_backtest(params: dict) -> dict | None:
    """Run a single backtest via tuner API. Returns metrics dict or None on error."""
    try:
        resp = requests.post(API_URL, json=params, timeout=120)
        if resp.status_code != 200:
            print(f"  API error {resp.status_code}: {resp.text[:200]}")
            return None
        data = resp.json()
        if "error" in data:
            print(f"  Backtest error: {data['error']}")
            return None
        summary = data.get("summary", {})
        annual = summary.get("annualReturn", 0)
        # API returns annualReturn as percentage (e.g. 78.02 = 78.02%)
        annual_frac = annual / 100.0 if abs(annual) > 1 else annual
        mdd = summary.get("maxDrawdown", 0)
        mdd_frac = mdd / 100.0 if abs(mdd) > 1 else mdd
        return {
            "annual": annual_frac,
            "sharpe": summary.get("sharpe", 0),
            "mdd": mdd_frac,
            "calmar": summary.get("calmar", 0),
            "sortino": summary.get("sortino", 0),
            "win_rate": summary.get("winRate", 0) / 100.0 if summary.get("winRate", 0) > 1 else summary.get("winRate", 0),
            "total_trades": summary.get("rebalanceCount", 0),
        }
    except Exception as e:
        print(f"  Request failed: {e}")
        return None


def main():
    print("=" * 80)
    print("REQ-190: 策略参数敏感性分析 — 单变量扫描")
    print(f"基线: weekly_trend, 3yr (2023-05 ~ 2026-05)")
    print("=" * 80)

    # Step 1: Run baseline
    print("\n--- 基线 ---")
    baseline_result = run_backtest(BASELINE)
    if baseline_result is None:
        print("FATAL: 基线回测失败，请确认 tuner 正在运行")
        sys.exit(1)
    print(f"  Annual={baseline_result['annual']:.1%}  Sharpe={baseline_result['sharpe']:.2f}  "
          f"MDD={baseline_result['mdd']:.1%}  Calmar={baseline_result['calmar']:.2f}  "
          f"Sortino={baseline_result['sortino']:.2f}")

    # Step 2: Sweep each parameter
    all_rows = []
    for param_key, display_name, values in SWEEPS:
        print(f"\n--- {display_name} ({param_key}) ---")
        baseline_val = BASELINE[param_key]
        print(f"  默认值: {baseline_val}, 扫描: {values}")

        for val in values:
            params = BASELINE.copy()
            params[param_key] = val
            result = run_backtest(params)
            if result is None:
                print(f"  {val:>6} => FAILED")
                continue

            delta_calmar = result["calmar"] - baseline_result["calmar"]
            row = {
                "param": display_name,
                "param_key": param_key,
                "value": val,
                "annual": result["annual"],
                "sharpe": result["sharpe"],
                "mdd": result["mdd"],
                "calmar": result["calmar"],
                "sortino": result["sortino"],
                "delta_calmar": delta_calmar,
                "win_rate": result["win_rate"],
                "trades": result["total_trades"],
            }
            all_rows.append(row)
            marker = " <-- default" if val == baseline_val else ""
            print(f"  {val:>6} => Calmar={result['calmar']:.2f} ({delta_calmar:+.2f})  "
                  f"Annual={result['annual']:.1%}  MDD={result['mdd']:.1%}{marker}")
            time.sleep(0.5)  # gentle pacing

    # Step 3: Sensitivity summary
    print("\n" + "=" * 80)
    print("敏感性汇总 (Calmar 变化幅度)")
    print("=" * 80)

    sensitivity = {}
    for param_key, display_name, values in SWEEPS:
        param_rows = [r for r in all_rows if r["param_key"] == param_key]
        if not param_rows:
            continue
        calmar_vals = [r["calmar"] for r in param_rows]
        calmar_range = max(calmar_vals) - min(calmar_vals)
        sensitivity[display_name] = calmar_range
        print(f"  {display_name:12s} | Calmar range = {calmar_range:.2f} "
              f"({min(calmar_vals):.2f} ~ {max(calmar_vals):.2f})")

    # Classify sensitivity
    print("\n参数分类:")
    for name, rng in sorted(sensitivity.items(), key=lambda x: -x[1]):
        if rng >= 1.0:
            level = "HIGH - sensitive"
        elif rng >= 0.3:
            level = "MED  - moderate"
        else:
            level = "LOW  - robust"
        print(f"  {level}  {name:12s}  range={rng:.2f}")

    # Step 4: Write CSV
    csv_path = DATA_DIR / "req190_sensitivity.csv"
    import pandas as pd
    df = pd.DataFrame(all_rows)
    df.to_csv(csv_path, index=False, encoding="utf-8")
    print(f"\nCSV saved to: {csv_path}")

    # Step 5: Write summary to REQ-190.md
    print("\n扫描完成。可更新 plans/REQ-190.md 记录结论。")


if __name__ == "__main__":
    main()
