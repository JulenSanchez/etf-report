"""Shared benchmark data helpers for quant scripts."""
from datetime import datetime
from pathlib import Path

import pandas as pd

from etf_report.core.trading_calendar import latest_allowed_close_date

PROJECT_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "config").is_dir() and (parent / "scripts").is_dir())
DATA_DIR = PROJECT_ROOT / "data" / "quant"
HS300_CACHE_PATH = DATA_DIR / "000300_daily.csv"  # unified path with quant_data_fetcher


def load_hs300_daily_cached(cache_path=HS300_CACHE_PATH):
    """Load HS300 daily data from local cache (unified 000300_daily.csv path)."""
    return _load_index_daily_cached("000300", "sh000300", cache_path)


# Index code → akshare symbol mapping
INDEX_SYMBOL_MAP = {
    "000016": "sh000016",   # SSE 50
    "000300": "sh000300",   # HS300
    "000905": "sh000905",   # CSI500
    "399006": "sz399006",   # ChiNext
}

INDEX_NAME_MAP = {
    "000016": "上证50",
    "000300": "沪深300",
    "000905": "中证500",
    "399006": "创业板指",
}

INDEX_CACHE_DIR = DATA_DIR


def load_index_daily_cached(code: str):
    """Load any index daily data from local cache, fetching if missing/stale.

    Args:
        code: Index code (000016, 000300, 000905, 399006)

    Returns:
        DataFrame with columns: date, open, high, low, close, volume
    """
    symbol = INDEX_SYMBOL_MAP.get(code)
    if symbol is None:
        raise ValueError("Unknown index code: {} (supported: {})".format(
            code, list(INDEX_SYMBOL_MAP.keys())))
    cache_path = INDEX_CACHE_DIR / "{}_daily.csv".format(code)
    return _load_index_daily_cached(code, symbol, cache_path)


def _load_index_daily_cached(code, symbol, cache_path):
    """Internal: load index daily data with cache logic."""
    cache_path = Path(cache_path)
    cached = None
    if cache_path.exists():
        try:
            cached = pd.read_csv(cache_path, parse_dates=["date"])
            cached = cached.sort_values("date").reset_index(drop=True)
        except Exception as e:
            print("  [WARN] {} cache read failed: {}".format(code, e))
            cached = None

    latest_allowed = latest_allowed_close_date()
    if cached is not None and len(cached) > 0:
        last_date = cached["date"].iloc[-1].strftime("%Y-%m-%d")
        cache_mtime = datetime.fromtimestamp(cache_path.stat().st_mtime).strftime("%Y-%m-%d")
        if last_date >= latest_allowed or cache_mtime == datetime.now().strftime("%Y-%m-%d"):
            print("  {} cache: {} rows ({})".format(code, len(cached), last_date))
            return cached

    try:
        import akshare as ak
        print("  {} cache stale/missing, fetching...".format(code))
        df = ak.stock_zh_index_daily(symbol=symbol)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(cache_path, index=False, encoding="utf-8")
        print("  {} cache updated: {} rows".format(code, len(df)))
        return df
    except Exception as e:
        if cached is not None and len(cached) > 0:
            print("  [WARN] {} fetch failed, using stale cache: {}".format(code, e))
            return cached
        raise


def build_hs300_pct(hs_daily, date_strs):
    """Normalize HS300 close to 100 on first matching date."""
    hs_map = dict(zip(hs_daily["date"].dt.strftime("%Y-%m-%d"), hs_daily["close"].astype(float)))
    anchor = None
    out = []
    for d in date_strs:
        if d in hs_map:
            if anchor is None:
                anchor = hs_map[d]
            out.append(round(hs_map[d] / anchor * 100, 2))
        else:
            out.append(out[-1] if out else 100.0)
    return out


def build_hs300_weekly(hs_daily):
    """Build Friday/week-ending HS300 weekly close DataFrame."""
    return build_index_weekly(hs_daily)


def build_index_weekly(daily_df):
    """Build Friday/week-ending weekly close DataFrame for any index."""
    df = daily_df.copy()
    df["week"] = df["date"].dt.isocalendar().year.astype(str) + "-" + df["date"].dt.isocalendar().week.astype(str).str.zfill(2)
    return df.groupby("week").last().reset_index()[["date", "close"]]


def build_ma_trend_cache(daily_df, weekly_df, period):
    """Build weekly MA above/below and MA direction lookup by daily date.

    Works for any index (not HS300-specific despite parameter names).
    """
    if daily_df is None or weekly_df is None:
        return None
    w = weekly_df.copy()
    ma_col = "ma{}".format(period)
    w[ma_col] = w["close"].rolling(period, min_periods=max(period // 2, 5)).mean()
    w["above"] = w["close"] >= w[ma_col]
    w["ma_rising"] = w[ma_col] > w[ma_col].shift(1)
    w = w.dropna(subset=[ma_col]).copy().sort_values("date")

    d = daily_df[["date"]].copy().sort_values("date")
    merged = pd.merge_asof(
        d,
        w[["date", "above", "ma_rising"]],
        on="date",
        direction="backward",
        tolerance=pd.Timedelta(days=6),
    ).dropna(subset=["above"])
    date_keys = merged["date"].dt.strftime("%Y-%m-%d")
    above_map = dict(zip(date_keys, merged["above"].astype("boolean").fillna(False).astype(bool)))
    rising_map = dict(zip(date_keys, merged["ma_rising"].astype("boolean").fillna(False).astype(bool)))
    return {"above": above_map, "ma_rising": rising_map}
