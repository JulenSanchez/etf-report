"""
ETF K 线数据拉取器 — 腾讯财经 fqkline API（前复权）。

输出：data/quant/{code}_daily.csv  (日线: date, open, close, high, low, volume, amount)
      data/quant/{code}_weekly.csv (周线: 同上)

三种模式:
  incremental (默认)  python quant_data_fetcher.py
      拉取 CSV 最新日期之后的新行。不覆盖已有数据。安全，可随时运行。
      约 2 分钟 / 40 支 ETF。

  patch               python quant_data_fetcher.py --start YYYY-MM-DD [--end YYYY-MM-DD]
      重新拉取指定日期范围，合并入现有 CSV（覆盖重叠行）。
      用于修正错误数据。end 默认为今天。
      例: python quant_data_fetcher.py --start 2026-05-13 --end 2026-05-14

  full                 python quant_data_fetcher.py --full
      丢弃现有 CSV，全量重新拉取。慢（约 10 分钟），用于重建整个数据集。

选项:
  --code CODE    只操作单支 ETF

合规: 3s 请求间隔 + 重试退避 + 收盘冷却规则（盘中不拉当天未完成 K 线）
"""
import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
import yaml

PROJECT_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "config").is_dir() and (parent / "scripts").is_dir())
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from trading_calendar import load_trading_calendar, latest_allowed_close_date
from etf_report.core.quant_data_utils import rebuild_weekly_from_daily

sys.stdout.reconfigure(encoding="utf-8")

# A-share market close time and cooling-off rule
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MIN = 0
COOL_OFF_MINUTES = 10  # only allow data >= close_time + cool_off (REQ-195: 15:10 即可拉取，为盘后交易预留时间)


def _latest_allowed_date(now=None) -> str:
    """Return the latest date (YYYY-MM-DD) for which closed K-line data is safe to fetch."""
    return latest_allowed_close_date(
        now=now,
        market_close_hour=MARKET_CLOSE_HOUR,
        market_close_minute=MARKET_CLOSE_MIN,
        cool_off_minutes=COOL_OFF_MINUTES,
    )

CONFIG_PATH = PROJECT_ROOT / "config" / "quant_universe.yaml"
DATA_DIR = PROJECT_ROOT / "data" / "quant"
FRESH_MARKER = DATA_DIR / ".fresh_today"

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


def _tx_request(tx_code: str, period: str, count: int,
                end_date: str = "", retries: int = MAX_RETRIES) -> list:
    """Tencent Finance API request with retry logic. Returns list of kline rows.
    period: 'daily' or 'weekly' (converted to 'day'/'week' for API)
    end_date: optional end date (YYYY-MM-DD) for backward pagination; empty = latest
    """
    # Convert internal period names to Tencent API format
    tx_period = "day" if period == "daily" else "week"
    # param format: {code},{period},{start},{end},{count},{qfq_type}
    for attempt in range(1, retries + 1):
        try:
            # Build URL directly — requests params dict encodes commas, breaking Tencent API
            full_url = f"{TX_KLINE_URL}?param={tx_code},{tx_period},,{end_date},{count},qfq"
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
                    start_date: str = None, end_date: str = None):
    """
    从腾讯财经 API 拉取 ETF 前复权 K 线。
    period: 'daily' | 'weekly'
    start_date: 增量拉取起始日期 (YYYY-MM-DD)，客户端过滤 (> start_date)
    end_date:   截止日期 (YYYY-MM-DD)，客户端过滤 (<= end_date)。
                盘中使用，确保不拉到当天未完成的K线。默认用 _latest_allowed_date()。
    返回 DataFrame: date, open, close, high, low, volume, amount
    """
    import pandas as pd

    tx_code = f"{MARKET_PREFIX.get(market, 'sz')}{code}"
    _orig_end_date = end_date  # save before pagination loop mutates it

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
        # Full fetch: paginate backwards to get ALL historical data
        # Tencent API returns rows up to end_date. To paginate:
        #   1. First request: end="" (latest) → get latest 800 rows
        #   2. Note earliest date in response
        #   3. Next request: end = earliest_date - 1 day → get 800 rows before that
        #   4. Repeat until batch < 800 (reached listing date)
        end_date = ""
        max_pages = 20  # safety: 20 * 800 = 16000 rows > 12 years daily

        for page in range(max_pages):
            batch = _tx_request(tx_code, period, TX_MAX_COUNT, end_date=end_date)
            if not batch:
                break

            all_rows.extend(batch)

            if len(batch) < TX_MAX_COUNT:
                # Fewer than max rows → reached the beginning
                break

            # Find earliest date in this batch to set end for next page
            earliest = batch[0][0]  # date is first field
            end_dt = datetime.strptime(earliest, "%Y-%m-%d") - timedelta(days=1)
            end_date = end_dt.strftime("%Y-%m-%d")

            # Rate limiting between pages
            time.sleep(1.0)
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

    # Deduplicate by date (pagination batches may overlap at boundaries)
    df = df.drop_duplicates(subset=["date"], keep="first").sort_values("date").reset_index(drop=True)

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

    # Only keep rows on or before the latest allowed close date (or explicit end_date)
    latest = _orig_end_date if _orig_end_date else _latest_allowed_date()
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


def _safe_date_filter(df, path_hint=""):
    """Strip rows with future dates or today's unconfirmed intraday data.
    Returns filtered DataFrame. Logs a warning when rows are stripped.
    """
    import pandas as pd
    from datetime import datetime
    if df.empty:
        return df
    df = df.copy()
    if "date" not in df.columns:
        return df
    df["_date_parsed"] = pd.to_datetime(df["date"])
    today = pd.Timestamp(datetime.now().strftime("%Y-%m-%d"))
    now = datetime.now()
    post_market = now.hour * 60 + now.minute >= 910  # 15:10

    # Always reject future dates
    future_mask = df["_date_parsed"] > today
    # Reject today's date during market hours (not yet confirmed close)
    today_mask = (df["_date_parsed"] == today) & (not post_market)

    drop_mask = future_mask | today_mask
    if drop_mask.any():
        dropped_dates = df.loc[drop_mask, "date"].unique()
        print("  [SAFE] Stripping {} rows with unconfirmed dates from {}: {}".format(
            drop_mask.sum(), path_hint or path, list(dropped_dates)))
        df = df[~drop_mask]
    df = df.drop(columns=["_date_parsed"])
    return df


def save_csv(df, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    df = _safe_date_filter(df, str(path))
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


SINA_BATCH_URL = "https://hq.sinajs.cn/list="
SINA_HEADERS = {"Referer": "https://finance.sina.com.cn/"}


def _fetch_sina_batch(codes: list) -> dict:
    """Fetch today's OHLCV for multiple ETFs via Sina batch API.
    Returns {code: {date, open, close, high, low, volume, amount}} for each ETF.
    Only returns data if market is closed (date field present in response).
    """
    if not codes:
        return {}
    # Build Sina code list: sh512400, sz159915, ...
    sina_codes = [f"{mkt}{code}" for code, mkt in codes]
    url = SINA_BATCH_URL + ",".join(sina_codes)
    try:
        resp = __import__('requests').get(url, headers=SINA_HEADERS, timeout=10)
        if resp.status_code != 200:
            return {}
    except Exception:
        return {}

    result = {}
    for line in resp.text.strip().split("\n"):
        if "=" not in line:
            continue
        try:
            sina_code = line.split("=")[0].replace("var hq_str_", "")
            # Extract code from sina_code (e.g., sh512400 → 512400)
            code = sina_code[2:]
            fields = line.split("=")[1].strip('";').split(",")
            if len(fields) < 10:
                continue
            date_str = fields[-3] if len(fields) > 3 else ""
            if not date_str or date_str == '""':
                continue  # market still open, no date field
            # During market hours Sina returns time (e.g. "10:21:13") instead of date.
            # Validate YYYY-MM-DD format — reject anything that isn't a real date.
            if not __import__('re').match(r'^\d{4}-\d{2}-\d{2}$', date_str):
                continue
            result[code] = {
                "date": date_str,
                "open": float(fields[1]),
                "close": float(fields[3]),
                "high": float(fields[4]),
                "low": float(fields[5]),
                "volume": int(float(fields[8])),
                "amount": float(fields[9]),
            }
        except (ValueError, IndexError):
            continue
    return result


def update_single(etf: dict, full: bool = False, end_date: str = None,
                  sina_batch: dict = None):
    """Update one ETF's daily + weekly data. Returns (daily_rows, weekly_rows, mode).
    end_date: exclusive end date (YYYY-MM-DD), passed to fetch_etf_kline to exclude
              incomplete intraday bars when called during market hours.
    sina_batch: pre-fetched Sina batch data {code: {date, open, close, ...}} for
                single-day incremental updates (much faster than per-ETF Tencent)."""
    code = etf["code"]
    market = etf["market"]
    name = etf["name"]

    daily_path = DATA_DIR / f"{code}_daily.csv"
    weekly_path = DATA_DIR / f"{code}_weekly.csv"

    if full:
        df_daily = fetch_etf_kline(code, market, "daily", end_date=end_date)
        save_csv(df_daily, daily_path)
        df_weekly = rebuild_weekly_from_daily(df_daily)
        save_csv(df_weekly, weekly_path)
        return len(df_daily), len(df_weekly), "full"

    # Incremental
    last_daily = get_last_date(daily_path)

    if last_daily is None:
        # First time (no CSV)
        df_daily = fetch_etf_kline(code, market, "daily", end_date=end_date)
        save_csv(df_daily, daily_path)
        df_weekly = rebuild_weekly_from_daily(df_daily)
        save_csv(df_weekly, weekly_path)
        return len(df_daily), len(df_weekly), "init"

    # Freshness check: require data up to the latest-allowed close date
    last_dt = datetime.strptime(last_daily, "%Y-%m-%d").date()
    expected = datetime.strptime(_latest_allowed_date(), "%Y-%m-%d").date()
    if last_dt >= expected:
        return 0, 0, "fresh"

    # Incremental: try Sina batch first, fallback to Tencent
    import pandas as pd
    if sina_batch and code in sina_batch:
        row = sina_batch[code]
        sina_date = datetime.strptime(row["date"], "%Y-%m-%d").date()
        if sina_date > last_dt and sina_date <= expected:
            # Sina has data newer than CSV AND not beyond cool-off → use it
            new_row = pd.DataFrame([row])
            append_csv(new_row, daily_path)
            full_daily = pd.read_csv(daily_path)
            df_weekly = rebuild_weekly_from_daily(full_daily)
            save_csv(df_weekly, weekly_path)
            return 1, 0, "sina+batch"

    # Tencent incremental (multi-day gap or Sina unavailable)
    df_daily = fetch_etf_kline(code, market, "daily", start_date=last_daily, end_date=end_date)
    new_daily = len(df_daily)

    if new_daily > 0:
        append_csv(df_daily, daily_path)

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


def patch_range(etf: dict, start_date: str, end_date: str):
    """Re-fetch a specific date range and merge into existing CSV (replacing overlapping rows).
    Returns (daily_rows_written, weekly_rows, "patch")."""
    code = etf["code"]
    market = etf["market"]
    name = etf["name"]

    import pandas as pd
    daily_path = DATA_DIR / f"{code}_daily.csv"
    weekly_path = DATA_DIR / f"{code}_weekly.csv"

    # Subtract 1 day from start because fetch_etf_kline uses > filter
    adj_start = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    df_new = fetch_etf_kline(code, market, "daily", start_date=adj_start, end_date=end_date)
    if df_new.empty:
        return 0, 0, "patch"

    df_new["date"] = pd.to_datetime(df_new["date"])

    if daily_path.exists():
        df_old = pd.read_csv(daily_path)
        df_old["date"] = pd.to_datetime(df_old["date"])
        start_dt = pd.Timestamp(start_date)
        end_dt = pd.Timestamp(end_date)
        mask = (df_old["date"] >= start_dt) & (df_old["date"] <= end_dt)
        df_merged = pd.concat([df_old[~mask], df_new], ignore_index=True)
    else:
        df_merged = df_new

    df_merged = df_merged.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
    df_merged["date"] = df_merged["date"].dt.strftime("%Y-%m-%d")
    save_csv(df_merged, daily_path)

    old_weekly_rows = 0
    if weekly_path.exists():
        try:
            old_weekly_rows = len(pd.read_csv(weekly_path, usecols=["date"]))
        except Exception:
            old_weekly_rows = 0
    weekly = rebuild_weekly_from_daily(df_merged)
    save_csv(weekly, weekly_path)
    new_weekly = max(len(weekly) - old_weekly_rows, 0)

    return len(df_new), new_weekly, "patch"


def main():
    load_trading_calendar()
    parser = argparse.ArgumentParser(description="ETF K-line data fetcher (Tencent Finance qfq)")
    parser.add_argument("--code", type=str, default=None, help="Only update specified ETF")
    parser.add_argument("--full", action="store_true", help="Full re-fetch all history")
    parser.add_argument("--start", type=str, default=None, help="Patch mode: start date (YYYY-MM-DD, inclusive)")
    parser.add_argument("--end", type=str, default=None, help="Patch mode: end date (YYYY-MM-DD, inclusive)")
    args = parser.parse_args()

    patch_mode = bool(args.start)
    if patch_mode and not args.end:
        args.end = datetime.now().strftime("%Y-%m-%d")

    universe = load_universe()
    if args.code:
        universe = [e for e in universe if e["code"] == args.code]

    if not universe:
        print(f"[ERROR] ETF not found: {args.code}")
        return

    if patch_mode:
        mode_label = f"patch {args.start}~{args.end}"
    elif args.full:
        mode_label = "full"
    else:
        mode_label = "incremental"
    print(f"=== ETF K-line fetch ({mode_label}) · {len(universe)} ETFs ===\n")

    # Global freshness check: skip entire loop if already updated today
    if not args.full and not patch_mode and FRESH_MARKER.exists():
        try:
            marker_date = FRESH_MARKER.read_text().strip()
            expected = _latest_allowed_date()
            if marker_date >= expected:
                print(f"  All {len(universe)} ETFs already fresh ({marker_date}), skipping.\n")
                print(f"=== Done: OK={len(universe)} (cached), FAIL=0 ===")
                return
        except Exception:
            pass

    # Pre-fetch Sina batch for incremental mode (single HTTP call for all ETFs).
    # During market hours Sina returns real-time price (no date) → not written to CSV.
    # After close Sina returns date field → written to CSV via gap==1 path.
    sina_batch = None
    if not args.full and not patch_mode:
        codes = [(e["code"], e["market"]) for e in universe]
        sina_batch = _fetch_sina_batch(codes)

    ok, fail, fresh = 0, 0, 0
    for i, etf in enumerate(universe, 1):
        code = etf["code"]
        name = etf["name"]

        try:
            print(f"  [{i:2d}/{len(universe)}] {name}({code}) ... ", end="", flush=True)
            if patch_mode:
                daily_rows, weekly_rows, mode = patch_range(etf, args.start, args.end)
            else:
                daily_rows, weekly_rows, mode = update_single(etf, full=args.full, sina_batch=sina_batch)
            if mode == "fresh":
                print(f"OK [fresh]")
                fresh += 1
            else:
                print(f"OK [{mode}] daily+{daily_rows} weekly+{weekly_rows}")
                ok += 1
                if i < len(universe):
                    time.sleep(3.0)

        except Exception as e:
            print(f"FAIL: {e}")
            fail += 1

    # Write freshness marker if all ETFs are up to date
    if fail == 0 and not args.full and not patch_mode:
        try:
            FRESH_MARKER.parent.mkdir(parents=True, exist_ok=True)
            FRESH_MARKER.write_text(datetime.now().strftime("%Y-%m-%d"))
        except Exception:
            pass

    total_ok = ok + fresh
    print(f"\n=== Done: OK={total_ok}, FAIL={fail} ===")

    # ── Fetch benchmark indices (always, alongside ETF data) ──
    fetch_benchmark_indices()


# ── Benchmark index fetching ────────────────────────────────────────────

BENCHMARK_INDICES = {
    "000016": "sh000016",   # SSE 50
    "000300": "sh000300",   # HS300
    "000905": "sh000905",   # CSI500
    "399006": "sz399006",   # ChiNext
}


def fetch_benchmark_indices():
    """Fetch all benchmark index daily data alongside ETF data.

    Uses the same freshness check as ETF data (latest_allowed_date).
    Called automatically at the end of every quant_data_fetcher run.
    Also used by benchmark_data.py on first access as a lazy fallback.
    """
    print("\n=== Benchmark indices ===\n")
    ok, fail = 0, 0
    for code, symbol in BENCHMARK_INDICES.items():
        cache_path = DATA_DIR / "{}_daily.csv".format(code)
        try:
            fresh = _update_index_csv(code, symbol, cache_path)
            if fresh:
                print("  [{}] {} ... OK [fresh]".format(code, INDEX_NAMES.get(code, "")))
            else:
                print("  [{}] {} ... OK [updated]".format(code, INDEX_NAMES.get(code, "")))
            ok += 1
        except Exception as e:
            print("  [{}] {} ... FAIL: {}".format(code, INDEX_NAMES.get(code, ""), e))
            fail += 1
    print("\n=== Indices: OK={}, FAIL={} ===".format(ok, fail))


INDEX_NAMES = {
    "000016": "上证50",
    "000300": "沪深300",
    "000905": "中证500",
    "399006": "创业板指",
}


def _update_index_csv(code, symbol, cache_path):
    """Update a single index CSV. Returns True if already fresh, False if updated."""
    import pandas as pd
    cache_path = Path(cache_path)

    cached = None
    if cache_path.exists():
        try:
            cached = pd.read_csv(cache_path, parse_dates=["date"])
            cached = cached.sort_values("date").reset_index(drop=True)
        except Exception:
            cached = None

    expected = _latest_allowed_date()
    if cached is not None and len(cached) > 0:
        last_date = cached["date"].iloc[-1].strftime("%Y-%m-%d")
        if last_date >= expected:
            return True  # Already fresh

    # Fetch full history (akshare returns all available data)
    import akshare as ak
    df = ak.stock_zh_index_daily(symbol=symbol)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path, index=False, encoding="utf-8")
    return False


if __name__ == "__main__":
    main()
