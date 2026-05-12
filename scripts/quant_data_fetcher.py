"""
REQ-177 M0.2: 27 支 ETF 历史 K 线数据拉取
用途：为三因子打分系统提供日线 + 周线历史数据

输出：data/quant/{code}_daily.csv  (日线: date, open, close, high, low, volume, amount)
      data/quant/{code}_weekly.csv (周线: 同上)

用法：
  python scripts/quant_data_fetcher.py              # 增量更新（默认）
  python scripts/quant_data_fetcher.py --full        # 全量重新拉取
  python scripts/quant_data_fetcher.py --code 512400 # 只更新一支

数据源：腾讯财经 fqkline API（前复权）
合规：3s 请求间隔 + 重试退避 + 收盘冷却规则
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
COOL_OFF_MINUTES = 10  # only allow data >= close_time + cool_off (REQ-195: 15:10 即可拉取，为盘后交易预留时间)

# Trading calendar (loaded from data/quant/trading_days_YYYY.txt)
_TRADING_DAYS_FETCHER = set()
_TD_LIST_FETCHER = []


def _load_trading_calendar_fetcher():
    """Load trading day calendar for the current year (+ adjacent years)."""
    global _TRADING_DAYS_FETCHER, _TD_LIST_FETCHER
    _TRADING_DAYS_FETCHER = set()
    _TD_LIST_FETCHER = []
    data_dir = Path(__file__).resolve().parent.parent / "data" / "quant"
    for year in [datetime.now().year - 1, datetime.now().year, datetime.now().year + 1]:
        p = data_dir / f"trading_days_{year}.txt"
        if p.exists():
            with open(p) as f:
                for line in f:
                    ds = line.strip()
                    if ds:
                        _TRADING_DAYS_FETCHER.add(ds)
    _TD_LIST_FETCHER = sorted(_TRADING_DAYS_FETCHER)


def _last_trading_day_fetcher(before=None) -> str:
    """Return the most recent trading day on or before `before` as YYYY-MM-DD."""
    d = before or datetime.now()
    if _TD_LIST_FETCHER:
        ds = d.strftime("%Y-%m-%d")
        lo, hi = 0, len(_TD_LIST_FETCHER) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if _TD_LIST_FETCHER[mid] <= ds:
                lo = mid + 1
            else:
                hi = mid - 1
        if hi >= 0:
            return _TD_LIST_FETCHER[hi]
    # Fallback: simple weekday
    d2 = d
    for _ in range(7):
        if d2.weekday() < 5:
            return d2.strftime("%Y-%m-%d")
        d2 -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def _latest_allowed_date() -> str:
    """Return the latest date (YYYY-MM-DD) for which closed K-line data is safe to fetch.

    After 15:10 on a trading day, today's close is available.
    Before 15:10 (or on a non-trading day), the latest allowed date is
    the last trading day.
    """
    now = datetime.now()
    close_time = now.replace(hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MIN,
                             second=0, microsecond=0)
    if now >= close_time + timedelta(minutes=COOL_OFF_MINUTES):
        return _last_trading_day_fetcher(now)
    else:
        return _last_trading_day_fetcher(now - timedelta(minutes=1))

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = SKILL_DIR / "config" / "quant_universe.yaml"
DATA_DIR = SKILL_DIR / "data" / "quant"

# Tencent Finance K-line API
TX_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
TX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Referer": "https://gu.qq.com/",
}
# Tencent code format: {market_prefix}{etf_code}, e.g. sz512400, sh510300
MARKET_PREFIX = {"sh": "sh", "sz": "sz"}
MAX_RETRIES = 3
RETRY_DELAY = 5.0
TX_MAX_COUNT = 800  # max rows per request


def load_universe(config_path: Path = CONFIG_PATH):
    with config_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("universe", [])


def _tx_request(tx_code: str, period: str, count: int, retries: int = MAX_RETRIES) -> list:
    """Tencent Finance API request with retry logic. Returns list of kline rows.
    period: 'daily' or 'weekly' (converted to 'day'/'week' for API)
    """
    # Convert internal period names to Tencent API format
    tx_period = "day" if period == "daily" else "week"
    # param format: {code},{period},{start},{end},{count},{qfq_type}
    param_str = f"{tx_code},{period},,,{count},qfq"
    for attempt in range(1, retries + 1):
        try:
            # Build URL directly — requests params dict encodes commas, breaking Tencent API
            full_url = f"{TX_KLINE_URL}?param={tx_code},{tx_period},,,{count},qfq"
            resp = requests.get(full_url, headers=TX_HEADERS, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == 0 and isinstance(data.get("data"), dict):
                    inner = data["data"][tx_code]
                    # Key varies: day->"day" or "qfqday", week->"week" or "qfqweek"
                    kline_key = None
                    for k in inner:
                        if tx_period == "day" and k in ("day", "qfqday"):
                            kline_key = k
                            break
                        if tx_period == "week" and k in ("week", "qfqweek"):
                            kline_key = k
                            break
                    rows = inner.get(kline_key, []) if kline_key else []
                    return rows
                # code != 0 or bad data
                if attempt < retries:
                    print(f"  API code={data.get('code')}, retry {attempt}/{retries}", end="", flush=True)
                    time.sleep(RETRY_DELAY * attempt)
                    continue
                return []
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
    return []


def _parse_tx_rows(rows: list) -> list[dict]:
    """Parse Tencent kline rows: [date, open, close, high, low, volume]."""
    parsed = []
    for row in rows:
        if len(row) < 6:
            continue
        vol = int(float(row[5]))
        close = float(row[2])
        parsed.append({
            "date": row[0],
            "open": float(row[1]),
            "close": close,
            "high": float(row[3]),
            "low": float(row[4]),
            "volume": vol,
            "amount": round(close * vol * 100, 2),  # estimate: close * volume * 100 shares
        })
    return parsed


def fetch_etf_kline(code: str, market: str, period: str = "daily",
                    start_date: str = None):
    """
    从腾讯财经 API 拉取 ETF 前复权 K 线。
    period: 'daily' | 'weekly'
    start_date: 增量拉取起始日期 (YYYY-MM-DD)，客户端过滤
    返回 DataFrame: date, open, close, high, low, volume, amount
    """
    import pandas as pd

    tx_code = f"{MARKET_PREFIX.get(market, 'sz')}{code}"

    # Determine how many rows to fetch
    if start_date:
        # Incremental: estimate rows needed (2x calendar days as safety margin)
        days_gap = (datetime.now() - datetime.strptime(start_date, "%Y-%m-%d")).days
        need_count = max(days_gap * 2, 20)
        need_count = min(need_count, TX_MAX_COUNT)
    else:
        # Full/init: need all data, may require multiple requests
        need_count = TX_MAX_COUNT

    # Fetch data (single request for incremental, paginated for full)
    all_rows = []
    if start_date is None:
        # Full fetch: paginate from oldest to newest
        # Tencent returns latest N rows, so we need to work backwards
        # Strategy: fetch MAX, check if we got the earliest data
        batch = _tx_request(tx_code, period, TX_MAX_COUNT)
        if batch:
            all_rows.extend(batch)
        # One batch of 800 should cover ~3 years of daily data for most ETFs
        # If more is needed, additional batches can be added
    else:
        # Incremental: just fetch the needed count
        batch = _tx_request(tx_code, period, need_count)
        if batch:
            all_rows.extend(batch)

    if not all_rows:
        return pd.DataFrame(columns=["date", "open", "close", "high", "low", "volume", "amount"])

    parsed = _parse_tx_rows(all_rows)
    if not parsed:
        return pd.DataFrame(columns=["date", "open", "close", "high", "low", "volume", "amount"])

    df = pd.DataFrame(parsed)

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

    # Client-side filtering (Tencent doesn't support server-side start_date)
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


def rebuild_weekly_from_daily(daily_df):
    """Build weekly OHLCV from daily data using each week's latest trading day.

    Tencent weekly K-line may lag during the current week. Rebuilding from
    local daily data keeps weekly factors/K-line aligned with the latest
    available trading day (e.g. Monday 2026-05-11 instead of prior Friday).
    """
    import pandas as pd
    if daily_df is None or daily_df.empty:
        return pd.DataFrame(columns=["date", "open", "close", "high", "low", "volume", "amount"])

    df = daily_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["_week"] = df["date"].dt.isocalendar().year.astype(str) + "-" + df["date"].dt.isocalendar().week.astype(str).str.zfill(2)

    weekly = df.groupby("_week", as_index=False).agg({
        "date": "last",
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "amount": "sum",
    })
    weekly = weekly[["date", "open", "close", "high", "low", "volume", "amount"]]
    weekly["date"] = weekly["date"].dt.strftime("%Y-%m-%d")
    return weekly


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
        df_weekly = rebuild_weekly_from_daily(df_daily)
        save_csv(df_weekly, weekly_path)
        return len(df_daily), len(df_weekly), "full"

    # Incremental
    last_daily = get_last_date(daily_path)
    last_weekly = get_last_date(weekly_path)

    if last_daily is None:
        # First time (no CSV)
        df_daily = fetch_etf_kline(code, market, "daily")
        save_csv(df_daily, daily_path)
        df_weekly = rebuild_weekly_from_daily(df_daily)
        save_csv(df_weekly, weekly_path)
        return len(df_daily), len(df_weekly), "init"

    # Incremental: only fetch daily rows after last_date, then rebuild weekly from local daily.
    # Rebuilding avoids Tencent weekly lag during an unfinished trading week.
    df_daily = fetch_etf_kline(code, market, "daily", start_date=last_daily)
    new_daily = len(df_daily)

    if new_daily > 0:
        append_csv(df_daily, daily_path)

    import pandas as pd
    full_daily = pd.read_csv(daily_path)
    df_weekly = rebuild_weekly_from_daily(full_daily)
    old_weekly_rows = 0
    if weekly_path.exists():
        try:
            old_weekly_rows = len(pd.read_csv(weekly_path, usecols=["date"]))
        except Exception:
            old_weekly_rows = 0
    save_csv(df_weekly, weekly_path)
    new_weekly = max(len(df_weekly) - old_weekly_rows, 0)

    return new_daily, new_weekly, "incremental"


def main():
    _load_trading_calendar_fetcher()
    parser = argparse.ArgumentParser(description="ETF K-line data fetcher (Tencent Finance qfq)")
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
