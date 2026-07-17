"""Shared trading calendar helpers for quant/report scripts."""
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "config").is_dir() and (parent / "scripts").is_dir())
DATA_DIR = PROJECT_ROOT / "data" / "quant"

_TRADING_DAYS = set()
_TD_LIST = []
_LOADED_YEARS = None


def load_trading_calendar(years=None):
    """Load trading days from data/quant/trading_days_YYYY.txt.

    If files are missing, auto-generates them via AKShare (one-time bootstrap).
    Falls back to weekday approximation (Mon-Fri) only if network is unavailable.
    """
    global _TRADING_DAYS, _TD_LIST, _LOADED_YEARS
    if years is None:
        now_year = datetime.now().year
        years = [now_year - 1, now_year, now_year + 1]
    years_key = tuple(years)
    if _LOADED_YEARS == years_key and _TD_LIST:
        return _TD_LIST

    days = set()
    missing_files = []
    for year in years:
        path = DATA_DIR / f"trading_days_{year}.txt"
        if path.exists():
            with path.open(encoding="utf-8") as f:
                for line in f:
                    ds = line.strip()
                    if ds and not ds.startswith("#"):
                        days.add(ds)
        else:
            missing_files.append(path)

    # Auto-generate missing calendar files via AKShare (self-healing bootstrap)
    if missing_files:
        import logging, sys as _sys
        _scripts_dir = str(PROJECT_ROOT / "scripts")
        if _scripts_dir not in _sys.path:
            _sys.path.insert(0, _scripts_dir)
        _log = logging.getLogger(__name__)
        _log.warning("Trading calendar files missing: %s — attempting auto-generation",
                     [p.name for p in missing_files])
        try:
            from generate_trading_calendar import fetch_trading_dates, generate_calendar_files
            generate_calendar_files(years)
            # Reload now that files exist
            for year in years:
                path = DATA_DIR / f"trading_days_{year}.txt"
                if path.exists():
                    with path.open(encoding="utf-8") as f:
                        for line in f:
                            ds = line.strip()
                            if ds:
                                days.add(ds)
            _log.info("Auto-generated %d trading calendar files", len(missing_files))
        except Exception as e:
            _log.warning("Auto-generation failed (%s), falling back to weekday approximation", e)

    _TRADING_DAYS = days
    _TD_LIST = sorted(days)
    _LOADED_YEARS = years_key
    return _TD_LIST


def is_trading_day(dt=None):
    """Return whether dt is a trading day; fall back to weekday if no calendar exists."""
    d = dt or datetime.now()
    if not _TD_LIST:
        load_trading_calendar()
    ds = d.strftime("%Y-%m-%d")
    if _TRADING_DAYS:
        return ds in _TRADING_DAYS
    return d.weekday() < 5


def last_trading_day(before=None):
    """Return the most recent trading day on or before `before` as YYYY-MM-DD."""
    d = before or datetime.now()
    if not _TD_LIST:
        load_trading_calendar()
    ds = d.strftime("%Y-%m-%d")
    if _TD_LIST:
        lo, hi = 0, len(_TD_LIST) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if _TD_LIST[mid] <= ds:
                lo = mid + 1
            else:
                hi = mid - 1
        if hi >= 0:
            return _TD_LIST[hi]

    d2 = d
    for _ in range(14):  # 14 days covers Spring Festival (~10 trading days max)
        if d2.weekday() < 5:
            return d2.strftime("%Y-%m-%d")
        d2 -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def latest_allowed_close_date(now=None, market_close_hour=15, market_close_minute=0, cool_off_minutes=10):
    """Return latest date whose closed K-line data is safe to fetch."""
    n = now or datetime.now()
    close_time = n.replace(hour=market_close_hour, minute=market_close_minute, second=0, microsecond=0)
    if n >= close_time + timedelta(minutes=cool_off_minutes):
        return last_trading_day(n)
    return last_trading_day(n - timedelta(days=1))
