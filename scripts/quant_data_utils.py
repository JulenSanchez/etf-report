"""Shared data helpers for quant scripts."""
from pathlib import Path

import pandas as pd

SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SKILL_DIR / "data" / "quant"


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
    Includes every ISO week that has at least one trading day.
    Bar dates = last trading day of the ISO week.
    """
    if daily_df is None or len(daily_df) == 0:
        return pd.DataFrame()
    df = daily_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["week"] = df["date"].dt.isocalendar().year.astype(str) + "-" + df["date"].dt.isocalendar().week.astype(str).str.zfill(2)

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
    return df.groupby("week").agg(**agg).reset_index(drop=True)


def get_price_on_date(all_daily, code, date, field="close"):
    """Return a price field for one code/date from an all_daily dict."""
    df = all_daily.get(code)
    if df is None or field not in df.columns:
        return None
    row = df[df["date"] == date]
    if len(row) == 0:
        return None
    return float(row[field].iloc[0])
