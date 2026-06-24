"""Shared data helpers for quant scripts."""
from pathlib import Path

import pandas as pd

PROJECT_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "config").is_dir() and (parent / "scripts").is_dir())
DATA_DIR = PROJECT_ROOT / "data" / "quant"


def load_etf_data(code, data_dir=DATA_DIR):
    """Load one ETF's daily and weekly OHLCV CSVs."""
    data_dir = Path(data_dir)
    daily_path = data_dir / f"{code}_daily.csv"
    weekly_path = data_dir / f"{code}_weekly.csv"
    if not daily_path.exists() or not weekly_path.exists():
        return None, None
    daily = pd.read_csv(daily_path, parse_dates=["date"])
    weekly = pd.read_csv(weekly_path, parse_dates=["date"])
    daily = daily.sort_values("date").reset_index(drop=True)
    weekly = weekly.sort_values("date").reset_index(drop=True)
    return daily, weekly


def rebuild_weekly_from_daily(daily_df):
    """Rebuild weekly OHLCV/amount bars from daily data.
    Only includes COMPLETE ISO weeks (Friday has occurred).
    The current incomplete week is excluded to prevent fake bars
    that break F1 checkpoint/freeze logic.
    Bar dates = Friday (last trading day) of the ISO week.
    """
    if daily_df is None or len(daily_df) == 0:
        return pd.DataFrame()
    df = daily_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["week"] = df["date"].dt.isocalendar().year.astype(str) + "-" + df["date"].dt.isocalendar().week.astype(str).str.zfill(2)
    df["dow"] = df["date"].dt.dayofweek  # 0=Mon .. 4=Fri

    # Exclude incomplete weeks. Use trading calendar when available,
    # so holiday-shortened weeks (e.g. Thu before holiday Fri) are
    # recognised as complete. Falls back to dayofweek if calendar missing.
    today = pd.Timestamp.now().normalize()
    has_future_td = False  # remaining trading days in this ISO week?
    try:
        from etf_report.core.trading_calendar import is_trading_day as _is_td
        mon = today - pd.Timedelta(days=today.dayofweek)
        has_future_td = any(_is_td(mon + pd.Timedelta(days=i)) for i in range(7) if mon + pd.Timedelta(days=i) > today)
    except Exception:
        has_future_td = today.dayofweek < 4  # fallback: Mon-Thu = incomplete
    if has_future_td:
        cur_iso = today.isocalendar()
        cur_week_str = f"{cur_iso.year}-{cur_iso.week:02d}"
        df = df[df["week"] != cur_week_str]

    agg = {
        "date": ("date", "last"),
        "open": ("open", "first"),
        "close": ("close", "last"),
        "high": ("high", "max"),
        "low": ("low", "min"),
        "volume": ("volume", "sum"),
    }
    if "amount" in df.columns:
        agg["amount"] = ("amount", "sum")
    result = df.groupby("week").agg(**agg).reset_index(drop=True)
    # Drop helper column if present
    result = result.drop(columns=["dow"], errors="ignore")
    return result


def get_price_on_date(all_daily, code, date, field="close"):
    """Return a price field for one code/date from an all_daily dict."""
    df = all_daily.get(code)
    if df is None or field not in df.columns:
        return None
    row = df[df["date"] == date]
    if len(row) == 0:
        return None
    return float(row[field].iloc[0])
