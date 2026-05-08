#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REQ-183 Layer 2: KDP (Key Decision Points) 评分

设计：
  - 读 data/market_events.json（Layer 1 输出）+ 调 Tuner /api/run 拿 signalHistory
  - 把 signalHistory 推断为"每日仓位序列"（调仓日之间仓位保持）
  - 对每个 rally/crash 事件，计算策略在该事件期间的"参与度 / 规避度"
  - 总分 = 0.6 × 主升参与度 + 0.4 × 大跌规避度

用法：
  python scripts/evaluate_kdp.py --params '{"w1":40,"w2":30,"w3":30,"w4":0,...}'
  或 import 后调用 evaluate_kdp(params, market_events) 直接得到 dict
"""

import argparse
import csv
import io
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import pandas as pd
from quant_backtest import load_etf_data
from data_cleaning import run_data_cleaning_pipeline

TUNER_URL = "http://localhost:5179/api/run"
EVENTS_PATH = SKILL_DIR / "data" / "market_events.json"

# ============================================================
# Score weights (rally vs crash)
# ============================================================
W_RALLY = 0.6   # 主升浪参与度权重
W_CRASH = 0.4   # 大跌规避度权重


# ============================================================
# Helpers
# ============================================================
def call_tuner(params, retries=2):
    body = json.dumps(params).encode("utf-8")
    req = urllib.request.Request(
        TUNER_URL, data=body, headers={"Content-Type": "application/json"}
    )
    last = None
    for _ in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(1)
    raise RuntimeError(f"Tuner call failed: {last}")


def load_market_events():
    with EVENTS_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# Cache: cleaned daily prices for each ETF (load once, reuse)
# ============================================================
_PRICE_CACHE = {}


def _get_cleaned_daily(code, events_by_code):
    if code in _PRICE_CACHE:
        return _PRICE_CACHE[code]
    daily, _ = load_etf_data(code)
    if daily is None:
        _PRICE_CACHE[code] = None
        return None
    events = events_by_code.get(code) or []
    if events:
        ci = {
            "dates": [pd.Timestamp(d).strftime("%Y-%m-%d") for d in daily["date"]],
            "kline": [[float(r["open"]), float(r["close"]), float(r["low"]), float(r["high"])]
                      for _, r in daily.iterrows()],
            "volumes": [int(v) for v in daily["volume"]] if "volume" in daily.columns else [],
        }
        cleaned = run_data_cleaning_pipeline(ci, events)
        out = daily.copy().reset_index(drop=True)
        for idx in range(len(out)):
            o, c, l, h = cleaned["kline"][idx]
            out.at[idx, "close"] = c
        daily = out
    _PRICE_CACHE[code] = daily
    return daily


def get_corporate_action_events():
    path = SKILL_DIR / "data" / "corporate_action_events.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f).get("events_by_code", {}) or {}


# ============================================================
# Daily position series from signalHistory
# ============================================================
def build_daily_position_series(signal_history, code, dates):
    """从 signalHistory 推算某只 ETF 的每日仓位（占总资产的比例 0~1）。

    调仓日之间仓位保持不变。
    """
    if not signal_history or not dates:
        return [0.0] * len(dates)

    pos_series = [0.0] * len(dates)
    cur_pos = 0.0
    sig_idx = 0
    sigs_sorted = sorted(signal_history, key=lambda s: s["date"])

    for i, d in enumerate(dates):
        d_str = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
        # 推进 sig_idx 直到 sig.date > d_str
        while sig_idx < len(sigs_sorted) and sigs_sorted[sig_idx]["date"] <= d_str:
            sig = sigs_sorted[sig_idx]
            detail = sig.get("detail", {}).get(code)
            cur_pos = (detail.get("position", 0) / 100.0) if detail else 0.0
            sig_idx += 1
        pos_series[i] = cur_pos

    return pos_series


# ============================================================
# Score one event
# ============================================================
def score_rally_event(event, signal_history, events_by_code):
    """主升浪事件得分。

    新评分逻辑：
      - 计算策略在该事件期间的"平均仓位"（每日仓位均值）
      - 与"max_holdings 上限对应的最大可持仓位"做对比
      - 即：默认 6 标的 = 满仓时单只 ~17%；策略平均 17% → 满分 100
      - 实际"参与度" = 平均仓位 / 期望理想仓位上限

    返回：{
      'event': 事件原始信息,
      'event_gain_pct': 事件总涨幅,
      'avg_position_pct': 策略期间平均仓位 (%),
      'strategy_gain_pct': 策略期间收益贡献,
      'participation': 参与度 0~1.x,
      'score': 0~100 分,
    }
    """
    code = event["code"]
    df = _get_cleaned_daily(code, events_by_code)
    if df is None:
        return None

    t_date = pd.Timestamp(event["trough_date"])
    p_date = pd.Timestamp(event["peak_date"])
    seg = df[(df["date"] >= t_date) & (df["date"] <= p_date)].reset_index(drop=True)
    if len(seg) < 2:
        return None

    daily_returns = seg["close"].pct_change().fillna(0).tolist()
    pos_series = build_daily_position_series(signal_history, code, seg["date"].tolist())

    # 平均仓位（不算第 0 天，因为 0 天涨幅 = 0）
    avg_pos = sum(pos_series[1:]) / max(1, len(pos_series) - 1) if len(pos_series) > 1 else 0
    avg_pos_pct = avg_pos * 100

    # 策略实际收益贡献
    strategy_contrib = sum(
        pos_series[i - 1] * daily_returns[i]
        for i in range(1, len(daily_returns))
    ) * 100

    event_gain = event["gain_pct"]
    if event_gain <= 0:
        return None

    # 参与度：平均仓位 / "理想满仓位"（17% = 1/6 standard max_holdings 下的单标的上限）
    # 这样如果策略平均持仓 17%，参与度 = 1.0 (满分)
    # 如果策略平均持仓 8.5%，参与度 = 0.5 (半参与)
    IDEAL_POSITION = 0.167  # 1/6
    participation = avg_pos / IDEAL_POSITION
    score = max(0, min(100, participation * 100))

    return {
        "event": event,
        "event_gain_pct": event_gain,
        "avg_position_pct": round(avg_pos_pct, 1),
        "strategy_gain_pct": round(strategy_contrib, 2),
        "participation": round(participation, 3),
        "score": round(score, 1),
    }


def score_crash_event(event, signal_history, events_by_code):
    """大跌事件得分。

    新评分逻辑：
      - 计算策略在该事件期间的"平均仓位"
      - 完全规避（仓位 = 0）→ 100 分
      - 满仓踩中（仓位 = 17%）→ 0 分
    """
    code = event["code"]
    df = _get_cleaned_daily(code, events_by_code)
    if df is None:
        return None

    p_date = pd.Timestamp(event["peak_date"])
    t_date = pd.Timestamp(event["trough_date"])
    seg = df[(df["date"] >= p_date) & (df["date"] <= t_date)].reset_index(drop=True)
    if len(seg) < 2:
        return None

    daily_returns = seg["close"].pct_change().fillna(0).tolist()
    pos_series = build_daily_position_series(signal_history, code, seg["date"].tolist())

    avg_pos = sum(pos_series[1:]) / max(1, len(pos_series) - 1) if len(pos_series) > 1 else 0
    avg_pos_pct = avg_pos * 100

    strategy_loss = -sum(
        pos_series[i - 1] * daily_returns[i]
        for i in range(1, len(daily_returns))
    ) * 100

    event_drop = abs(event["drop_pct"])
    if event_drop <= 0:
        return None

    # 规避度：1 - 平均仓位 / IDEAL_POSITION
    # 完全规避 (avg_pos=0) → 1.0 → 100 分
    # 满仓踩中 (avg_pos=17%) → 0.0 → 0 分
    IDEAL_POSITION = 0.167
    avoidance = 1 - avg_pos / IDEAL_POSITION
    score = max(-50, min(100, avoidance * 100))  # 负分 = 反向加仓

    return {
        "event": event,
        "event_drop_pct": -event_drop,
        "avg_position_pct": round(avg_pos_pct, 1),
        "strategy_loss_pct": round(strategy_loss, 2),
        "avoidance": round(avoidance, 3),
        "score": round(score, 1),
    }


# ============================================================
# Main evaluation function
# ============================================================
def evaluate_kdp(params, market_events=None, verbose=False):
    """评估单个参数组合的 KDP 得分。

    返回 dict: {
      'rally_score': 平均主升参与度得分,
      'crash_score': 平均大跌规避度得分,
      'kdp_total': 综合分,
      'rally_details': [...],
      'crash_details': [...],
    }
    """
    if market_events is None:
        market_events = load_market_events()

    events_by_code = get_corporate_action_events()
    resp = call_tuner(params)
    if resp.get("error"):
        return {"error": resp["error"]}

    signal_history = resp.get("signalHistory", [])
    if not signal_history:
        return {"error": "no signalHistory"}

    # 只评估在回测窗口内的事件
    backtest_start = params.get("start_date", "1900-01-01")
    backtest_end   = params.get("end_date",   "2999-12-31")

    rally_results = []
    for ev in market_events.get("rallies", []):
        # 事件必须落在回测窗口内
        if ev["trough_date"] < backtest_start or ev["peak_date"] > backtest_end:
            continue
        r = score_rally_event(ev, signal_history, events_by_code)
        if r:
            rally_results.append(r)

    crash_results = []
    for ev in market_events.get("crashes", []):
        if ev["peak_date"] < backtest_start or ev["trough_date"] > backtest_end:
            continue
        r = score_crash_event(ev, signal_history, events_by_code)
        if r:
            crash_results.append(r)

    rally_score = sum(r["score"] for r in rally_results) / len(rally_results) if rally_results else 0
    crash_score = sum(r["score"] for r in crash_results) / len(crash_results) if crash_results else 0
    kdp_total = W_RALLY * rally_score + W_CRASH * crash_score

    out = {
        "rally_count": len(rally_results),
        "crash_count": len(crash_results),
        "rally_score": round(rally_score, 1),
        "crash_score": round(crash_score, 1),
        "kdp_total": round(kdp_total, 1),
        "rally_details": rally_results if verbose else None,
        "crash_details": crash_results if verbose else None,
    }
    return out


# ============================================================
# CLI
# ============================================================
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--params", type=str, help="JSON params dict")
    p.add_argument("--csv", type=str, help="CSV path: 评估 CSV 中所有组合（增量加 KDP 列后导出新 CSV）")
    p.add_argument("--top", type=int, default=30, help="若给 --csv，则只评估 top N 行")
    args = p.parse_args()

    market_events = load_market_events()
    print(f"已加载 {len(market_events['rallies'])} 主升事件 + {len(market_events['crashes'])} 大跌事件")
    print()

    if args.csv:
        # Bulk evaluation: rank rows by Sharpe, pick top N, evaluate KDP for each
        in_csv = Path(args.csv)
        rows = []
        with in_csv.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                for k in ["w1","w2","w3","w4","totalReturn","annualReturn","maxDrawdown",
                          "sharpe","sortino","calmar","winRate","rebalanceCount"]:
                    r[k] = float(r[k])
                rows.append(r)
        # Score by Sharpe
        rows.sort(key=lambda r: r["sharpe"], reverse=True)
        candidates = rows[:args.top]
        print(f"评估 Top {len(candidates)} 候选 (按 Sharpe 排序)...")

        # Need start/end date — use today and 1y back (consistent with quant_param_search)
        from datetime import timedelta
        today = datetime.now().date()
        end_date = today.strftime("%Y-%m-%d")
        start_date = (today - timedelta(days=365)).strftime("%Y-%m-%d")

        out_csv = in_csv.parent / f"{in_csv.stem}_with_kdp.csv"
        out_fields = list(candidates[0].keys()) + ["kdp_total","kdp_rally","kdp_crash","rally_n","crash_n"]
        with out_csv.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=out_fields)
            w.writeheader()
            t_start = time.time()
            for i, row in enumerate(candidates, 1):
                params = {
                    "w1": int(row["w1"]), "w2": int(row["w2"]),
                    "w3": int(row["w3"]), "w4": int(row["w4"]),
                    "bias": 0,
                    "conf_type": "quadratic",
                    "dead_zone": 25, "full_zone": 65,
                    "max_holdings": 6, "disc_step": 5,
                    "ema_period": 16, "rsi_period": 14, "vol_window": 20,
                    "f1_sensitivity": 8.0, "f3_sensitivity": 1.0, "f2_dead_zone": 1.0,
                    "start_date": start_date, "end_date": end_date,
                }
                kdp = evaluate_kdp(params, market_events)
                if "error" in kdp:
                    print(f"  [{i}/{len(candidates)}] w={params['w1'],params['w2'],params['w3'],params['w4']} KDP FAIL: {kdp['error']}")
                    continue
                row.update({
                    "kdp_total": kdp["kdp_total"],
                    "kdp_rally": kdp["rally_score"],
                    "kdp_crash": kdp["crash_score"],
                    "rally_n": kdp["rally_count"],
                    "crash_n": kdp["crash_count"],
                })
                w.writerow(row)
                f.flush()
                if i % 5 == 0 or i == len(candidates):
                    eta = (time.time() - t_start) / i * (len(candidates) - i)
                    print(f"  [{i}/{len(candidates)}] w=({int(row['w1'])},{int(row['w2'])},{int(row['w3'])},{int(row['w4'])}) "
                          f"sharpe={row['sharpe']:.2f} kdp={kdp['kdp_total']:.1f} "
                          f"(rally={kdp['rally_score']:.0f}/{kdp['rally_count']} crash={kdp['crash_score']:.0f}/{kdp['crash_count']}) "
                          f"ETA {eta/60:.1f}min")
        print(f"\n✓ KDP-augmented CSV: {out_csv}")
        return

    if args.params:
        params = json.loads(args.params)
        result = evaluate_kdp(params, market_events, verbose=True)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print("用法：--params '{...}' 评估单个组合，或 --csv path 批量评估")


if __name__ == "__main__":
    main()
