"""Shared benchmark data helpers for quant scripts.

REQ-384: ETF daily CSV is the primary data source (Sina pipeline, clean
volume/amount).  All benchmark keys are ETF codes (510300, 510050, 510500,
159915).  akshare `stock_zh_index_daily` is fallback when ETF CSV is missing.
"""
from datetime import datetime
from pathlib import Path

import pandas as pd

from etf_report.core.trading_calendar import latest_allowed_close_date

PROJECT_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "config").is_dir() and (parent / "scripts").is_dir())
DATA_DIR = PROJECT_ROOT / "data" / "quant"

# ── Benchmark ETF mapping (primary keys) ─────────────────────────────────

# ETF code → akshare symbol (fallback when ETF CSV is missing)
BENCHMARK_ETF_TO_AKSHARE = {
    "510050": "sh000016",   # 上证50
    "510300": "sh000300",   # 沪深300
    "510500": "sh000905",   # 中证500
    "159915": "sz399006",   # 创业板指
}

# ETF code → display name
BENCHMARK_ETF_NAMES = {
    "510050": "上证50",
    "510300": "沪深300",
    "510500": "中证500",
    "159915": "创业板指",
}

# All supported benchmark ETF codes
BENCHMARK_ETF_CODES = list(BENCHMARK_ETF_TO_AKSHARE.keys())

# Default (HS300 ETF)
DEFAULT_BENCHMARK_ETF = "510300"


def load_etf_as_benchmark(etf_code: str):
    """Load ETF daily CSV.  Returns None if missing."""
    path = DATA_DIR / "{}_daily.csv".format(etf_code)
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, parse_dates=["date"])
        return df.sort_values("date").reset_index(drop=True)
    except Exception:
        return None


def load_benchmark_daily(etf_code: str = DEFAULT_BENCHMARK_ETF):
    """Load benchmark ETF daily data.  Falls back to akshare if CSV missing.

    This replaces the old load_hs300_daily_cached() — all callers should
    migrate to this function with an ETF code argument.
    """
    df = load_etf_as_benchmark(etf_code)
    if df is not None:
        print("  {} (ETF) {} rows (Sina pipeline)".format(etf_code, len(df)))
        return df

    # Fallback: akshare
    symbol = BENCHMARK_ETF_TO_AKSHARE.get(etf_code)
    if symbol is None:
        raise ValueError("Unknown benchmark ETF: {} (supported: {})".format(
            etf_code, BENCHMARK_ETF_CODES))
    return _load_index_daily_cached(etf_code, symbol)


def _load_index_daily_cached(code, symbol):
    """Internal: akshare fallback.  Writes to a separate cache path
    so it never contaminates the ETF CSV (which is Sina-pipeline only)."""
    cache_path = DATA_DIR / "{}_daily_ak.csv".format(code)
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
        print("  {} cache stale/missing, fetching akshare...".format(code))
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


# ── Backward-compat aliases (kept for existing callers that haven't migrated) ──

# Old index code → ETF code.  Used by code that still passes index codes.
LEGACY_INDEX_TO_ETF = {
    "000016": "510050",
    "000300": "510300",
    "000905": "510500",
    "399006": "159915",
}


def load_hs300_daily_cached(cache_path=None):
    """Legacy alias.  Use load_benchmark_daily('510300') instead."""
    return load_benchmark_daily("510300")


def load_index_daily_cached(code: str):
    """Legacy alias.  Maps old index code → ETF code, then loads ETF CSV.

    Kept so existing callers (quant_backtest.py etc.) don't break.
    """
    etf_code = LEGACY_INDEX_TO_ETF.get(code, code)
    return load_benchmark_daily(etf_code)


# ── Legacy mapping dicts (for reference; prefer BENCHMARK_ETF_* above) ──

INDEX_SYMBOL_MAP = {k: v for k, v in LEGACY_INDEX_TO_ETF.items()}  # index→ETF
INDEX_NAME_MAP = {
    "510050": "上证50",
    "510300": "沪深300",
    "510500": "中证500",
    "159915": "创业板指",
}
INDEX_CACHE_DIR = DATA_DIR


def build_hs300_pct(hs_daily, date_strs):
    """Normalize close to 100 on first matching date."""
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
    """Build Friday/week-ending weekly close DataFrame."""
    return build_index_weekly(hs_daily)


def build_index_weekly(daily_df):
    """Build Friday/week-ending weekly close DataFrame for any index."""
    if daily_df is None:
        return None
    df = daily_df.copy()
    df["week"] = df["date"].dt.isocalendar().year.astype(str) + "-" + df["date"].dt.isocalendar().week.astype(str).str.zfill(2)
    return df.groupby("week").last().reset_index()[["date", "close"]]


def build_ma_trend_cache(daily_df, weekly_df, period):
    """Build weekly MA above/below and MA direction lookup by daily date."""
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
