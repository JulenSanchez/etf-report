"""
REQ-177 M0.2: 25 支 ETF 历史 K 线数据拉取
用途：为三因子打分系统提供日线 + 周线历史数据

输出：data/quant/{code}_daily.csv  (日线: date, open, high, low, close, volume, amount)
      data/quant/{code}_weekly.csv (周线: 同上)

用法：
  python scripts/quant_data_fetcher.py              # 增量更新（默认）
  python scripts/quant_data_fetcher.py --full        # 全量重新拉取
  python scripts/quant_data_fetcher.py --code 512400 # 只更新一支

数据源：东方财富 push2his API（前复权）
反爬对策：自定义 UA + Referer + start_date 服务端过滤 + 3s 间隔 + 重试
"""
import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
import yaml

sys.stdout.reconfigure(encoding="utf-8")

# A-share market close time and cooling-off rule
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MIN = 0
COOL_OFF_MINUTES = 60  # only allow data >= close_time + cool_off


def _latest_allowed_date() -> str:
    """Return the latest date (YYYY-MM-DD) for which closed K-line data is safe to fetch.

    Rule: only include a date if the market has been closed for at least
    COOL_OFF_MINUTES (default 60) minutes.  So for a 15:00 close, data
    becomes available at 16:00 on the same day; before 16:00 the latest
    allowed date is the previous trading day.

    This is a conservative check — it doesn't know the trading-day calendar,
    so on a non-trading day the check is still safe (current time is always
    well past 16:00, so yesterday is allowed).
    """
    now = datetime.now()
    close_time = now.replace(hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MIN,
                             second=0, microsecond=0)
    if now >= close_time + timedelta(minutes=COOL_OFF_MINUTES):
        return now.strftime("%Y-%m-%d")
    else:
        return (now - timedelta(days=1)).strftime("%Y-%m-%d")

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = SKILL_DIR / "config" / "quant_universe.yaml"
DATA_DIR = SKILL_DIR / "data" / "quant"

# East Money K-line API
EM_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
EM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
}
# market code -> secid prefix (1=SH, 0=SZ)
MARKET_PREFIX = {"sh": "1", "sz": "0"}
MAX_RETRIES = 3
RETRY_DELAY = 5.0


def load_universe(config_path: Path = CONFIG_PATH):
    with config_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("universe", [])


def _em_request(params: dict, retries: int = MAX_RETRIES) -> dict | None:
    """East Money API request with retry logic."""
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(EM_KLINE_URL, params=params, headers=EM_HEADERS, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("data") and data["data"].get("klines") is not None:
                    return data
                # Empty data (e.g. future date) — not an error
                return data
            print(f"  HTTP {resp.status_code}", end="", flush=True)
        except requests.exceptions.ConnectionError as e:
            if "RemoteDisconnected" in str(e) or "ConnectionAborted" in str(e):
                if attempt < retries:
                    wait = RETRY_DELAY * attempt
                    print(f"  connection refused, retry {attempt}/{retries} in {wait:.0f}s", end="", flush=True)
                    time.sleep(wait)
                    continue
            raise
        except requests.exceptions.Timeout:
            if attempt < retries:
                print(f"  timeout, retry {attempt}/{retries}", end="", flush=True)
                time.sleep(RETRY_DELAY)
                continue
            raise
    return None


def fetch_etf_kline(code: str, market: str, period: str = "daily",
                    start_date: str = None):
    """
    从东方财富 API 拉取 ETF 前复权 K 线。
    period: 'daily' | 'weekly'
    start_date: 增量拉取起始日期 (YYYY-MM-DD)，服务端过滤
    返回 DataFrame: date, open, high, low, close, volume, amount
    """
    import pandas as pd

    secid = f"{MARKET_PREFIX.get(market, '1')}.{code}"

    # start_date/end_date: YYYYMMDD format for East Money API
    beg = start_date.replace("-", "") if start_date else "19700101"
    end = "20500101"

    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
        "klt": "101",   # daily
        "fqt": "1",     # qfq (forward-adjusted)
        "beg": beg,
        "end": end,
    }

    data = _em_request(params)
    if data is None:
        raise RuntimeError(f"East Money API failed after {MAX_RETRIES} retries for {code}")

    klines = data.get("data", {}).get("klines", [])
    if not klines:
        # No data in range — return empty DataFrame with correct columns
        return pd.DataFrame(columns=["date", "open", "close", "high", "low", "volume", "amount"])

    # Parse klines: "date,open,close,high,low,volume,amount"
    rows = []
    for kline in klines:
        parts = kline.split(",")
        if len(parts) >= 7:
            rows.append({
                "date": parts[0],
                "open": float(parts[1]),
                "close": float(parts[2]),
                "high": float(parts[3]),
                "low": float(parts[4]),
                "volume": int(parts[5]),
                "amount": float(parts[6]),
            })

    df = pd.DataFrame(rows)

    if period == "weekly":
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        weekly = df.resample("W-FRI").agg(
            {"open": "first", "high": "max", "low": "min",
             "close": "last", "volume": "sum", "amount": "sum"}
        ).dropna()
        weekly = weekly.reset_index()
        df = weekly

    # Ensure date column is datetime for filtering
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])

    # Safety filter (server should already filter, but just in case)
    if start_date:
        cutoff = pd.Timestamp(start_date)
        df = df[df["date"] > cutoff].copy()

    # Only keep rows on or before the latest allowed close date
    latest = _latest_allowed_date()
    df = df[df["date"] <= pd.Timestamp(latest)].copy()

    # Final output: string dates
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    return df


def get_last_date(csv_path: Path):
    """Read the last date from an existing CSV. Returns YYYY-MM-DD string or None."""
    import pandas as pd
    if not csv_path.exists():
        return None
    try:
        df = pd.read_csv(csv_path, usecols=["date"], parse_dates=["date"])
        if df.empty:
            return None
        return df["date"].max().strftime("%Y-%m-%d")
    except Exception:
        return None


def save_csv(df, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")


def append_csv(new_df, path: Path):
    """Append new data to existing CSV, deduplicate by date."""
    import pandas as pd
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not new_df.empty:
        old_df = pd.read_csv(path, parse_dates=["date"])
        new_df = new_df.copy()
        new_df["date"] = pd.to_datetime(new_df["date"])
        combined = pd.concat([old_df, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["date"], keep="last")
        combined = combined.sort_values("date").reset_index(drop=True)
        combined["date"] = combined["date"].dt.strftime("%Y-%m-%d")
        combined.to_csv(path, index=False, encoding="utf-8")
    else:
        new_df.to_csv(path, index=False, encoding="utf-8")


def update_single(etf: dict, full: bool = False):
    """Update one ETF's daily + weekly data. Returns (daily_rows, weekly_rows, mode)."""
    code = etf["code"]
    market = etf["market"]
    name = etf["name"]

    daily_path = DATA_DIR / f"{code}_daily.csv"
    weekly_path = DATA_DIR / f"{code}_weekly.csv"

    if full:
        df_daily = fetch_etf_kline(code, market, "daily")
        save_csv(df_daily, daily_path)
        df_weekly = fetch_etf_kline(code, market, "weekly")
        save_csv(df_weekly, weekly_path)
        return len(df_daily), len(df_weekly), "full"

    # Incremental
    last_daily = get_last_date(daily_path)
    last_weekly = get_last_date(weekly_path)

    if last_daily is None:
        # First time (no CSV)
        df_daily = fetch_etf_kline(code, market, "daily")
        save_csv(df_daily, daily_path)
        df_weekly = fetch_etf_kline(code, market, "weekly")
        save_csv(df_weekly, weekly_path)
        return len(df_daily), len(df_weekly), "init"

    # Incremental: only fetch after last_date
    df_daily = fetch_etf_kline(code, market, "daily", start_date=last_daily)
    df_weekly = fetch_etf_kline(code, market, "weekly", start_date=last_weekly)

    new_daily = len(df_daily)
    new_weekly = len(df_weekly)

    if new_daily > 0:
        append_csv(df_daily, daily_path)
    if new_weekly > 0:
        append_csv(df_weekly, weekly_path)

    return new_daily, new_weekly, "incremental"


def main():
    parser = argparse.ArgumentParser(description="ETF K-line data fetcher (East Money qfq)")
    parser.add_argument("--code", type=str, default=None, help="Only update specified ETF")
    parser.add_argument("--full", action="store_true", help="Full re-fetch (default: incremental)")
    args = parser.parse_args()

    universe = load_universe()
    if args.code:
        universe = [e for e in universe if e["code"] == args.code]

    if not universe:
        print(f"[ERROR] ETF not found: {args.code}")
        return

    mode_label = "full" if args.full else "incremental"
    print(f"=== ETF K-line fetch ({mode_label}) · {len(universe)} ETFs ===\n")

    ok, fail = 0, 0
    for i, etf in enumerate(universe, 1):
        code = etf["code"]
        name = etf["name"]

        try:
            print(f"  [{i:2d}/{len(universe)}] {name}({code}) ... ", end="", flush=True)
            daily_rows, weekly_rows, mode = update_single(etf, full=args.full)
            print(f"OK [{mode}] daily+{daily_rows} weekly+{weekly_rows}")
            ok += 1

            if i < len(universe):
                time.sleep(3.0)

        except Exception as e:
            print(f"FAIL: {e}")
            fail += 1

    print(f"\n=== Done: OK={ok}, FAIL={fail} ===")


if __name__ == "__main__":
    main()
