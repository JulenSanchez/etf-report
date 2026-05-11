"""
run_scenarios.py — 可复用回测运行器

用法：
  # 跑默认4组（两个preset），结果缓存到 outputs/cache/
  python scripts/run_scenarios.py

  # 指定preset和时间范围
  python scripts/run_scenarios.py --presets weekly_trend daily_aggressive --start 2023-01-01 --end 2026-05-08

  # 强制重跑（忽略缓存）
  python scripts/run_scenarios.py --force

  # 从分析脚本中调用
  from run_scenarios import load_result
  nav, signals = load_result("daily_aggressive", "2023-01-01", "2026-05-08")
"""
import sys
import os
import pickle
import argparse
import time
from pathlib import Path
from multiprocessing import Pool, cpu_count

# 确保能找到同目录的其他模块
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

CACHE_DIR = SCRIPT_DIR.parent / "outputs" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_PRESETS = ["weekly_trend", "daily_aggressive"]
DEFAULT_START   = "2023-01-01"
DEFAULT_END     = "2026-05-08"


def cache_key(preset: str, start: str, end: str) -> str:
    return f"{preset}__{start}__{end}"


def cache_path(preset: str, start: str, end: str) -> Path:
    return CACHE_DIR / f"{cache_key(preset, start, end)}.pkl"


def load_result(preset: str, start: str = DEFAULT_START, end: str = DEFAULT_END):
    """从缓存加载结果。如果不存在则先跑回测再缓存。"""
    cp = cache_path(preset, start, end)
    if cp.exists():
        with open(cp, "rb") as f:
            return pickle.load(f)
    # 不存在则运行
    result = _run_one((preset, start, end))
    return result


def _run_one(args):
    """子进程入口：跑单个preset回测，返回 (nav_df, signal_history)"""
    preset, start, end = args
    # 子进程需要重新设置 sys.path
    sys.path.insert(0, str(SCRIPT_DIR))
    from quant_backtest import run_backtest

    # 抑制 run_backtest 内部的进度print
    import io
    class _Sink(io.TextIOBase):
        def write(self, s): return len(s)
        def flush(self): pass

    old_stdout = sys.stdout
    sys.stdout = _Sink()
    try:
        nav, signals = run_backtest(start_date=start, end_date=end, preset=preset)
    finally:
        sys.stdout = old_stdout

    # 写缓存
    cp = cache_path(preset, start, end)
    with open(cp, "wb") as f:
        pickle.dump((nav, signals), f)

    return nav, signals


def run_all(presets=None, start=DEFAULT_START, end=DEFAULT_END, force=False, parallel=True):
    """
    并行跑多个preset，命中缓存则跳过。
    返回 dict: {preset: (nav_df, signal_history)}
    """
    if presets is None:
        presets = DEFAULT_PRESETS

    # 区分哪些需要跑、哪些读缓存
    to_run = []
    cached  = {}
    for p in presets:
        cp = cache_path(p, start, end)
        if not force and cp.exists():
            print(f"  [缓存命中] {p}")
            with open(cp, "rb") as f:
                cached[p] = pickle.load(f)
        else:
            to_run.append(p)

    if not to_run:
        return cached

    print(f"  需要跑 {len(to_run)} 个preset: {to_run}")

    if parallel and len(to_run) > 1:
        workers = min(len(to_run), cpu_count())
        print(f"  使用 {workers} 个进程并行...")
        args = [(p, start, end) for p in to_run]
        t0 = time.time()
        with Pool(processes=workers) as pool:
            results = pool.map(_run_one, args)
        print(f"  并行完成，耗时 {time.time()-t0:.1f}s")
        for p, r in zip(to_run, results):
            cached[p] = r
    else:
        for p in to_run:
            print(f"  [运行] {p} ...")
            t0 = time.time()
            cached[p] = _run_one((p, start, end))
            print(f"    完成，耗时 {time.time()-t0:.1f}s")

    return cached


def print_stats(results, start, end):
    """打印各preset的基础统计"""
    import pandas as pd
    import numpy as np

    print(f"\n回测区间: {start} ~ {end}")
    print(f"{'策略':<22} {'总收益':>8} {'年化':>8} {'MDD':>8} {'Calmar':>8} {'Sharpe':>8}")
    print("-" * 66)

    for preset, (nav_df, _) in results.items():
        nav   = nav_df.set_index("date")["nav"]
        total = nav.iloc[-1] / nav.iloc[0] - 1
        peak  = nav.cummax()
        mdd   = ((nav - peak) / peak).min()
        days  = (nav.index[-1] - nav.index[0]).days
        ann   = (1 + total) ** (365 / max(days, 1)) - 1
        calmar = ann / abs(mdd) if mdd != 0 else float("nan")
        weekly = nav.resample("W").last().pct_change(fill_method=None).dropna()
        sharpe = weekly.mean() / weekly.std() * (52**0.5) if weekly.std() > 0 else float("nan")
        print(f"  {preset:<20} {total:>+7.1%} {ann:>+8.1%} {mdd:>8.1%} {calmar:>8.2f} {sharpe:>8.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ETF量化回测运行器")
    parser.add_argument("--presets", nargs="+", default=DEFAULT_PRESETS)
    parser.add_argument("--start",   default=DEFAULT_START)
    parser.add_argument("--end",     default=DEFAULT_END)
    parser.add_argument("--force",   action="store_true", help="忽略缓存强制重跑")
    parser.add_argument("--no-parallel", action="store_true", help="串行模式（调试用）")
    args = parser.parse_args()

    print(f"presets: {args.presets}  {args.start}~{args.end}  force={args.force}")
    results = run_all(
        presets=args.presets,
        start=args.start,
        end=args.end,
        force=args.force,
        parallel=not args.no_parallel,
    )
    print_stats(results, args.start, args.end)
