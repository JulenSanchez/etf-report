#!/usr/bin/env python3
"""删除 ETF CSV 中指定日期范围的行，用于强制重新拉取数据。
用法:
  python scripts/strip_csv_dates.py 2026-06-01              # 删单日
  python scripts/strip_csv_dates.py 2026-06-01 2026-06-02   # 删范围
  python scripts/strip_csv_dates.py --dry-run 2026-06-01    # 预览不执行
"""
import sys, os, glob, argparse
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data", "quant")

parser = argparse.ArgumentParser(description="Strip CSV rows by date range")
parser.add_argument("dates", nargs="+", help="Date(s) to strip: single or start end")
parser.add_argument("--dry-run", action="store_true", help="Preview only, don't write")
args = parser.parse_args()

if len(args.dates) == 1:
    targets = {args.dates[0]}
else:
    start, end = args.dates[0], args.dates[1]
    targets = {str(d)[:10] for d in pd.date_range(start, end)}

csvs = sorted(glob.glob(os.path.join(DATA_DIR, "*_daily.csv")))
if not csvs:
    print("No CSV files found"); sys.exit(1)

total_removed = 0
for path in csvs:
    df = pd.read_csv(path)
    before = len(df)
    df = df[~df["date"].astype(str).str[:10].isin(targets)]
    removed = before - len(df)
    if removed > 0:
        total_removed += removed
        code = os.path.basename(path).replace("_daily.csv", "")
        if args.dry_run:
            print(f"  [DRY-RUN] {code}: would remove {removed} rows")
        else:
            df.to_csv(path, index=False)

action = "Would remove" if args.dry_run else "Removed"
print(f"{action} {total_removed} rows across {len(csvs)} CSVs")
