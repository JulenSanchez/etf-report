#!/usr/bin/env python3
"""Compare direct preset backtest with Tuner-contract backtest.

This is a guardrail for keeping quant_universe.yaml, quant_contract.py,
quant_tuner.py and quant_backtest.py aligned.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import yaml

sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "config").is_dir() and (parent / "scripts").is_dir())
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from etf_report.core import quant_contract as qc
from quant_backtest import count_actual_rebalances, run_backtest

CONFIG_PATH = PROJECT_ROOT / "config" / "quant_universe.yaml"


def load_quant_config(path=CONFIG_PATH):
    with Path(path).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def summarize_result(nav_df, signal_history):
    if nav_df is None or len(nav_df) == 0:
        raise ValueError("empty nav_df")

    initial = float(nav_df["nav"].iloc[0])
    final = float(nav_df["nav"].iloc[-1])
    total_return = (final / initial - 1.0) * 100.0
    drawdown = (nav_df["nav"] - nav_df["nav"].cummax()) / nav_df["nav"].cummax() * 100.0

    return {
        "start_date": nav_df["date"].iloc[0].strftime("%Y-%m-%d"),
        "end_date": nav_df["date"].iloc[-1].strftime("%Y-%m-%d"),
        "trading_days": int(len(nav_df)),
        "final_nav": round(final, 6),
        "total_return": round(float(total_return), 6),
        "max_drawdown": round(float(drawdown.min()), 6),
        "rebalance_count": int(count_actual_rebalances(signal_history)),
        "rebalance_days": int(len(signal_history)),
        "signal_dates": [sig["date"].strftime("%Y-%m-%d") for sig in signal_history[:5]],
        "last_signal_date": signal_history[-1]["date"].strftime("%Y-%m-%d") if signal_history else None,
        "last_positions": signal_history[-1].get("positions", {}) if signal_history else {},
    }


def compare_summaries(a, b, tolerance=1e-6):
    numeric_keys = ["final_nav", "total_return", "max_drawdown"]
    exact_keys = ["trading_days", "rebalance_count", "rebalance_days", "signal_dates", "last_signal_date", "last_positions"]

    diffs = {}
    ok = True

    for key in numeric_keys:
        delta = abs(float(a[key]) - float(b[key]))
        diffs[key] = round(delta, 10)
        if delta > tolerance:
            ok = False

    for key in exact_keys:
        same = a[key] == b[key]
        diffs[key] = 0 if same else {"direct": a[key], "contract": b[key]}
        if not same:
            ok = False

    return ok, diffs


def run_direct(preset, start, end):
    nav_df, signal_history, _extra = run_backtest(
        start_date=start,
        end_date=end,
        preset=preset,
        return_details=False,
        return_debug=False,
    )
    return summarize_result(nav_df, signal_history)


def run_contract(cfg, preset, start, end):
    preset_cfg = cfg.get("presets", {}).get(preset)
    if not preset_cfg:
        raise ValueError(f"Preset not found: {preset}")

    params = qc.preset_to_tuner_params(preset, preset_cfg, cfg.get("confidence", {}))
    validation_error = qc.validate_tuner_params(params)
    if validation_error:
        raise ValueError(f"Invalid tuner params derived from preset: {validation_error}")

    config_override = qc.tuner_params_to_config_override(params)
    nav_df, signal_history, _extra = run_backtest(
        start_date=start,
        end_date=end,
        preset=preset,
        config_override=config_override,
        return_details=False,
        return_debug=False,
    )
    return summarize_result(nav_df, signal_history)


def run_check(preset, start, end, tolerance=1e-6):
    cfg = load_quant_config()
    direct = run_direct(preset, start, end)
    contract = run_contract(cfg, preset, start, end)
    ok, diffs = compare_summaries(direct, contract, tolerance=tolerance)
    return {"ok": ok, "preset": preset, "start": start, "end": end, "direct": direct, "contract": contract, "diffs": diffs}


def main():
    parser = argparse.ArgumentParser(description="Quant backtest consistency check")
    parser.add_argument("--preset", default="zen-1")
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--tolerance", type=float, default=1e-6)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = run_check(args.preset, args.start, args.end, tolerance=args.tolerance)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Preset: {result['preset']}")
        print(f"Window: {result['start']} -> {result['end'] or result['direct']['end_date']}")
        print("\nDirect preset:")
        print(json.dumps(result["direct"], ensure_ascii=False, indent=2))
        print("\nTuner contract:")
        print(json.dumps(result["contract"], ensure_ascii=False, indent=2))
        print("\nDiffs:")
        print(json.dumps(result["diffs"], ensure_ascii=False, indent=2))
        print("\n" + ("PASS" if result["ok"] else "FAIL"))

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
