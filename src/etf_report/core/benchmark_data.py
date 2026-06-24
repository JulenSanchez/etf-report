"""Shared benchmark data helpers for quant scripts."""
from datetime import datetime
from pathlib import Path

import pandas as pd

from etf_report.core.trading_calendar import latest_allowed_close_date

PROJECT_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "config").is_dir() and (parent / "scripts").is_dir())
DATA_DIR = PROJECT_ROOT / "data" / "quant"
HS300_CACHE_PATH = DATA_DIR / "hs300_daily.csv"


def load_hs300_daily_cached(cache_path=HS300_CACHE_PATH):
    """Load HS300 daily data from local cache, refreshing only when missing/stale."""
    cache_path = Path(cache_path)
    cached = None
    if cache_path.exists():
        try:
            cached = pd.read_csv(cache_path, parse_dates=["date"])
            cached = cached.sort_values("date").reset_index(drop=True)
        except Exception as e:
            print(f"  [WARN] HS300 cache read failed: {e}")
            cached = None

    latest_allowed = latest_allowed_close_date()
    if cached is not None and len(cached) > 0:
        last_date = cached["date"].iloc[-1].strftime("%Y-%m-%d")
        cache_mtime = datetime.fromtimestamp(cache_path.stat().st_mtime).strftime("%Y-%m-%d")
        if last_date >= latest_allowed or cache_mtime == datetime.now().strftime("%Y-%m-%d"):
            print(f"  HS300 cache: {len(cached)} rows ({last_date})")
            return cached

    try:
        import akshare as ak
        print("  HS300 cache stale/missing, fetching...")
        hs = ak.stock_zh_index_daily(symbol="sh000300")
        hs["date"] = pd.to_datetime(hs["date"])
        hs = hs.sort_values("date").reset_index(drop=True)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        hs.to_csv(cache_path, index=False, encoding="utf-8")
        print(f"  HS300 cache updated: {len(hs)} rows")
        return hs
    except Exception as e:
        if cached is not None and len(cached) > 0:
            print(f"  [WARN] HS300 fetch failed, using stale cache: {e}")
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
    hs = hs_daily.copy()
    hs["week"] = hs["date"].dt.isocalendar().year.astype(str) + "-" + hs["date"].dt.isocalendar().week.astype(str).str.zfill(2)
    return hs.groupby("week").last().reset_index()[["date", "close"]]


def build_ma_trend_cache(hs_daily, hs_weekly, period):
    """Build HS300 weekly MA above/below and MA direction lookup by daily date."""
    if hs_daily is None or hs_weekly is None:
        return None
    w = hs_weekly.copy()
    ma_col = f"ma{period}"
    w[ma_col] = w["close"].rolling(period, min_periods=max(period // 2, 5)).mean()
    w["above"] = w["close"] >= w[ma_col]
    w["ma_rising"] = w[ma_col] > w[ma_col].shift(1)
    w = w.dropna(subset=[ma_col]).copy().sort_values("date")

    d = hs_daily[["date"]].copy().sort_values("date")
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
