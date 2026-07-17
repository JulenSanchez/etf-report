#!/usr/bin/env python3
"""Generate trading_days_{year}.txt files from AKShare Sina trading calendar.

Usage:
  python scripts/generate_trading_calendar.py              # generate for current year ±1
  python scripts/generate_trading_calendar.py --years 2020-2027  # custom range
  python scripts/generate_trading_calendar.py --all        # all available years (1990+)

Output: data/quant/trading_days_{YYYY}.txt (one date per line, YYYY-MM-DD)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Resolve project root (same logic as paths.py)
_current = Path(__file__).resolve()
for _parent in _current.parents:
    if (_parent / "config").is_dir() and (_parent / "scripts").is_dir():
        PROJECT_ROOT = _parent
        break
else:
    PROJECT_ROOT = _current.parents[2]

DATA_DIR = PROJECT_ROOT / "data" / "quant"


def fetch_trading_dates():
    """Fetch all historical trading dates from AKShare. Returns list of YYYY-MM-DD strings."""
    try:
        import akshare as ak
        df = ak.tool_trade_date_hist_sina()
        # AKShare may return datetime.date objects — normalize to YYYY-MM-DD strings
        dates = []
        for v in df["trade_date"]:
            if hasattr(v, "strftime"):
                dates.append(v.strftime("%Y-%m-%d"))
            else:
                dates.append(str(v)[:10])
        return sorted(dates)
    except ImportError:
        print("ERROR: akshare not installed. Run: pip install akshare", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: failed to fetch trading calendar: {e}", file=sys.stderr)
        sys.exit(1)


def generate_calendar_files(years, data_dir=DATA_DIR):
    """Write trading_days_{year}.txt for each year."""
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    all_dates = fetch_trading_dates()
    print(f"Fetched {len(all_dates)} trading days from AKShare")

    by_year = {}
    for ds in all_dates:
        year = ds[:4]
        by_year.setdefault(year, []).append(ds)

    generated = 0
    for year in sorted(years):
        year_str = str(year)
        path = data_dir / f"trading_days_{year_str}.txt"
        dates = by_year.get(year_str, [])
        with path.open("w", encoding="utf-8") as f:
            if dates:
                f.write("\n".join(dates) + "\n")
            else:
                # Write placeholder to prevent repeated auto-generation attempts.
                # This file will naturally fill when the API has data for this year.
                f.write(f"# No trading days available yet for {year_str} (API gap)\n")
        status = f"{len(dates)} days" if dates else "placeholder (no data yet)"
        print(f"  {year_str}: {status} → {path}")
        generated += 1

    print(f"\nGenerated {generated} calendar files in {data_dir}")
    return generated


def main():
    from datetime import datetime as _dt

    p = argparse.ArgumentParser(description="Generate trading calendar files")
    p.add_argument("--years", default=None,
                   help="Year range, e.g. 2020-2027 (inclusive)")
    p.add_argument("--all", action="store_true",
                   help="Generate for all available years (1990+)")
    p.add_argument("--data-dir", default=str(DATA_DIR),
                   help="Output directory (default: data/quant)")
    args = p.parse_args()

    if args.all:
        years = range(1990, _dt.now().year + 2)
    elif args.years:
        parts = args.years.split("-")
        if len(parts) == 2:
            years = range(int(parts[0]), int(parts[1]) + 1)
        else:
            years = [int(y) for y in args.years.split(",")]
    else:
        y = _dt.now().year
        years = range(y - 1, y + 2)  # default: ±1 year

    generate_calendar_files(years, args.data_dir)


if __name__ == "__main__":
    main()
