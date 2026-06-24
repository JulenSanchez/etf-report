from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "config").is_dir() and (parent / "scripts").is_dir())
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from etf_report.core import trading_calendar as _impl
from etf_report.core.trading_calendar import *  # noqa: F401,F403


def __getattr__(name):
    return getattr(_impl, name)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Trading calendar helper")
    parser.add_argument("--is-trading-day", action="store_true", help="exit 0 if today is a trading day, else 1")
    args = parser.parse_args()

    if args.is_trading_day:
        raise SystemExit(0 if _impl.is_trading_day() else 1)
