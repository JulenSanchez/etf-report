"""
REQ-177 M0.2: 25 支 ETF 历史 K 线数据拉取
用途：为三因子打分系统提供日线 + 周线历史数据

输出：data/quant/{code}_daily.csv  (日线: date, open, high, low, close, volume, amount)
      data/quant/{code}_weekly.csv (周线: 同上)

用法：
  python scripts/quant_data_fetcher.py          # 拉全部 25 支
  python scripts/quant_data_fetcher.py --code 512400  # 只拉一支
  python scripts/quant_data_fetcher.py --skip-existing  # 跳过已有
"""
import argparse
import sys
import time
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = SKILL_DIR / "config" / "quant_universe.yaml"
DATA_DIR = SKILL_DIR / "data" / "quant"


def load_universe(config_path: Path = CONFIG_PATH):
    with config_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("universe", [])


def fetch_etf_kline(code: str, market: str, period: str = "daily"):
    """
    用 akshare fund_etf_hist_sina 拉 ETF 历史 K 线。
    period: 'daily' | 'weekly'
    返回 DataFrame: date, open, high, low, close, volume
    """
    import akshare as ak
    import pandas as pd

    symbol = f"{market}{code}"

    if period == "daily":
        df = ak.fund_etf_hist_sina(symbol=symbol)
    elif period == "weekly":
        # akshare 没有直接的周线接口，从日线聚合
        df = ak.fund_etf_hist_sina(symbol=symbol)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        weekly = df.resample("W-FRI").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
        ).dropna()
        weekly = weekly.reset_index()
        weekly["date"] = weekly["date"].dt.strftime("%Y-%m-%d")
        return weekly

    return df


def save_csv(df, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="REQ-177 M0.2: ETF K 线数据拉取")
    parser.add_argument("--code", type=str, default=None, help="只拉指定 ETF")
    parser.add_argument("--skip-existing", action="store_true", help="跳过已有文件")
    args = parser.parse_args()

    universe = load_universe()
    if args.code:
        universe = [e for e in universe if e["code"] == args.code]

    if not universe:
        print(f"[ERROR] 未找到 ETF: {args.code}")
        return

    print(f"=== REQ-177 M0.2: 拉取 {len(universe)} 支 ETF K 线数据 ===\n")

    ok, fail = 0, 0
    for i, etf in enumerate(universe, 1):
        code = etf["code"]
        market = etf["market"]
        name = etf["name"]

        daily_path = DATA_DIR / f"{code}_daily.csv"
        weekly_path = DATA_DIR / f"{code}_weekly.csv"

        if args.skip_existing and daily_path.exists() and weekly_path.exists():
            print(f"  [{i:2d}/25] {name}({code}) -- SKIP (already exists)")
            ok += 1
            continue

        try:
            print(f"  [{i:2d}/25] {name}({code}) ... ", end="", flush=True)

            # 日线
            df_daily = fetch_etf_kline(code, market, "daily")
            save_csv(df_daily, daily_path)

            # 周线（从日线聚合）
            df_weekly = fetch_etf_kline(code, market, "weekly")
            save_csv(df_weekly, weekly_path)

            print(f"OK (daily={len(df_daily)} rows, weekly={len(df_weekly)} rows)")
            ok += 1

            # 友好访问
            if i < len(universe):
                time.sleep(1.0)

        except Exception as e:
            print(f"FAIL: {e}")
            fail += 1

    print(f"\n=== 完成: OK={ok}, FAIL={fail} ===")


if __name__ == "__main__":
    main()
