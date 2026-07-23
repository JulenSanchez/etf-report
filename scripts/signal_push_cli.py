#!/usr/bin/env python3
"""
Signal push (CLI, no Tuner).
Used by GitHub Actions for remote backup push when local PC is offline.

Flow: trading-day check → full data fetch → backtest → Server酱 push
"""
import os, sys, subprocess, time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import requests
import yaml
from trading_calendar import is_trading_day
from quant_backtest import run_backtest, load_config

DRY_RUN = "--dry-run" in sys.argv
QUIET = "--quiet" in sys.argv


def log(msg):
    if not QUIET:
        print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def get_sendkey():
    """Read Server酱 sendkey: env var first, then secrets.yaml fallback."""
    env_key = os.environ.get("SERVERCHAN_SENDKEY", "")
    if env_key:
        return env_key

    secrets_path = PROJECT_ROOT / "config" / "secrets.yaml"
    if secrets_path.exists():
        with open(secrets_path, "r", encoding="utf-8") as f:
            sec = yaml.safe_load(f) or {}
        return sec.get("publish", {}).get("serverchan", {}).get("sendkey", "")
    return ""


def load_etf_names():
    with open(PROJECT_ROOT / "config" / "quant_universe.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return {e["code"]: e.get("name", e["code"]) for e in cfg.get("universe", [])}


def short(code, names):
    return names.get(code, code).replace("ETF", "")


def main():
    log("=" * 50)
    log("Signal Push CLI (no-Tuner mode)")
    now = datetime.now()

    # ── Stage 0: Pre-flight ──
    if not is_trading_day():
        log("SKIP: Not a trading day")
        return 0
    log(f"Trading day: YES ({now:%Y-%m-%d})")

    sendkey = get_sendkey()
    if not sendkey:
        log("ERROR: Server酱 sendkey not configured (set SERVERCHAN_SENDKEY env var or config/secrets.yaml)")
        return 1
    log("Server酱 sendkey: configured")

    # ── Stage 1: Full data fetch ──
    log("=" * 50)
    log("Stage 1: Full data fetch")
    t0 = time.time()
    fetcher = str(PROJECT_ROOT / "scripts" / "quant_data_fetcher.py")
    result = subprocess.run(
        [sys.executable, fetcher, "--full"],
        cwd=str(PROJECT_ROOT),
        capture_output=not QUIET,
        text=True,
        timeout=600,
    )
    elapsed = time.time() - t0
    if not QUIET:
        print(result.stdout)
    if result.returncode != 0:
        log(f"ERROR: Data fetch failed with exit code {result.returncode}")
        if result.stderr:
            log(f"  stderr: {result.stderr[:500]}")
        return 1
    log(f"  Fetch completed ({elapsed:.0f}s)")

    # ── Stage 2: Backtest ──
    log("=" * 50)
    log("Stage 2: Run backtest (gam-0)")
    # Verify config loading
    cfg = load_config(preset="gam-0")
    cc = cfg.get("confidence", {})
    log(f"  conf_type={cc.get('type')} bull={cc.get('ma_bull_pos')} bear={cc.get('ma_bear_pos')} period={cc.get('ma_trend_period')}")
    t0 = time.time()
    start = f"{now.year}-05-01"
    end = now.strftime("%Y-%m-%d")
    log(f"  Window: {start} ~ {end}")

    nav_df, signal_history, extra = run_backtest(
        preset="gam-0",
        start_date=start,
        end_date=end,
        return_details=True,
        verbose=not QUIET,
    )
    elapsed = time.time() - t0
    log(f"  AR={extra['annual_return']:.1f}%  Sharpe={extra['sharpe']:.2f}  "
        f"MDD={extra['max_drawdown']:.1f}%  ({elapsed:.0f}s)")

    # ── Stage 3: Build signal table ──
    log("=" * 50)
    log("Stage 3: Build execution table")

    etf_names = load_etf_names()
    latest = signal_history[-1]
    detail = latest.get("detail", {})
    positions = latest.get("actual_positions", latest.get("positions", {}))

    buy_list = []
    for code, target in sorted(positions.items(), key=lambda x: -x[1]):
        if target > 0.005:
            d = detail.get(code, {}) if detail else {}
            price = float(d.get("price", 0)) if d else 0.0
            if price <= 0:
                log(f"  WARN: {code} has no price, skipping")
                continue
            buy_list.append({
                "code": code,
                "name": short(code, etf_names),
                "target": target,
                "price": price,
                "targetPct": f"{round(target * 100)}%",
            })

    if not buy_list:
        log("ERROR: No buy positions — signal is empty")
        return 1
    log(f"  Buy positions: {len(buy_list)}")

    # ── Stage 4: Build markdown table (same format as preclose_push.py) ──
    AMOUNTS = list(range(500000, 605000, 10000))

    lines = [
        f"## 实盘调仓执行参照表",
        "",
        f"**策略**: 赌徒 (远端兜底) | **日期**: {now:%Y-%m-%d} | **窗口**: {start}~{end}",
        f"**回测**: AR={extra['annual_return']:.0f}% Sharpe={extra['sharpe']:.2f} MDD={extra['max_drawdown']:.0f}% 总敞口={latest.get('total_target',0)*100:.0f}% regime={latest.get('regime','?')} avg_conf={latest.get('avg_confidence',0):.2f}",
        "",
    ]

    col_labels = [f"{b['name']} {b['code']}" for b in buy_list]
    lines.append(f"|  | {' | '.join(col_labels)} |")
    lines.append(f"|--------|{''.join('------|' for _ in buy_list)}")

    target_cols = [f"{b['targetPct']}" for b in buy_list]
    lines.append(f"| 目标 | {' | '.join(target_cols)} |")

    price_cols = [f"{b['price']:.3f}" for b in buy_list]
    lines.append(f"| 现价 | {' | '.join(price_cols)} |")

    for amt in AMOUNTS:
        cols = [f"**{amt // 10000}w**"]
        for b in buy_list:
            alloc = amt * b["target"]
            shares = int(alloc / b["price"] / 100) * 100
            cols.append(f"{alloc / 10000:.1f}w / {shares:,}")
        lines.append(f"| {' | '.join(cols)} |")

    content_str = "\n".join(lines)

    # ── Stage 5: Push ──
    log("=" * 50)
    if DRY_RUN:
        log("Stage 5: DRY RUN — skipping push")
        print()
        print(content_str)
    else:
        log("Stage 5: Push to WeChat (Server酱)")
        title = f"{now:%m/%d} 赌徒 调仓信号 (远端)"
        r = requests.post(
            f"https://sctapi.ftqq.com/{sendkey}.send",
            data={"title": title, "desp": content_str},
            timeout=15,
        )
        resp = r.json()
        if resp.get("code") == 0:
            pushid = resp.get("data", {}).get("pushid", "?")
            log(f"Push sent OK (id={pushid})")
        else:
            log(f"ERROR: Push failed — {resp}")
            return 1

    log("=" * 50)
    log("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
