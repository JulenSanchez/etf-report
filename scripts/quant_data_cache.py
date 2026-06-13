"""
Shared data cache for backtest engine.
Loads all ETF CSV data once into memory, reusable across multiple backtest calls.
Supports multiprocessing via fork-based copy-on-write (processes inherit the cache).
"""
import sys, os, hashlib, json, time
from pathlib import Path
from datetime import datetime
from typing import Optional

PROJECT_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "config").is_dir() and (parent / "scripts").is_dir())
DATA_DIR = PROJECT_ROOT / "data" / "quant"
CACHE_DIR = PROJECT_ROOT / "data" / "backtest_cache"

from quant_data_utils import load_etf_data as _load_etf_csv
from benchmark_data import load_hs300_daily_cached, build_hs300_weekly, build_ma_trend_cache


class BacktestDataCache:
    """One-time load of all ETF CSVs + benchmarks. Designed for fork-based sharing."""

    def __init__(self):
        self.all_daily = {}
        self.all_weekly = {}
        self.hs300_pct = None
        self.eq_weight_pct = None
        self.market_regimes = None
        self.ma_trend_cache = {}
        self._loaded = False

    def load(self, universe: list, ma_periods: list = None):
        """Load all data from disk. Call once before parallel work."""
        if self._loaded:
            return

        t0 = time.time()
        n = len(universe)
        for i, etf in enumerate(universe):
            code = etf["code"]
            daily, weekly = _load_etf_csv(code, DATA_DIR)
            if daily is not None and len(daily) > 0:
                self.all_daily[code] = daily
                self.all_weekly[code] = weekly

        print(f"  [Cache] {len(self.all_daily)}/{n} ETFs loaded ({time.time()-t0:.1f}s)")

        # Benchmarks
        self.hs300_pct = load_hs300_daily_cached()
        if self.hs300_pct is not None and len(self.hs300_pct) > 0:
            weekly = build_hs300_weekly(self.hs300_pct)
            self.hs300_pct["pct_change"] = self.hs300_pct["close"].pct_change()

        self._loaded = True

    def get_preloaded(self) -> dict:
        """Build the preloaded dict expected by run_backtest() (all_daily + all_weekly)."""
        return {
            "all_daily": dict(self.all_daily),
            "all_weekly": dict(self.all_weekly),
        }

    def load_regimes(self, market_regimes: dict):
        self.market_regimes = market_regimes

    def load_ma_cache(self, period: int, cache: dict):
        self.ma_trend_cache[period] = cache


# ============================================================
# Parallel backtest runner
# ============================================================

def _run_one_backtest(args: dict):
    """Worker function for ProcessPoolExecutor. Must be at module level for pickling."""
    preset = args["preset"]
    start = args["start"]
    end = args["end"]
    execution_timing = args.get("execution_timing", "next_open")
    config_override = args.get("config_override")
    universe_filter = args.get("universe_filter")
    preloaded = args.get("preloaded")

    from quant_backtest import run_backtest as _rb
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        nav, sig, ext = _rb(
            start_date=start, end_date=end,
            preset=preset, execution_timing=execution_timing,
            preloaded=preloaded, config_override=config_override,
            universe_filter=universe_filter, return_details=False,
        )
    final_nav = float(nav["nav"].iloc[-1])
    days = max(1, (nav["date"].iloc[-1] - nav["date"].iloc[0]).days)
    cagr = ((final_nav / 1_000_000) ** (365 / days) - 1) * 100
    dd = (nav["nav"] - nav["nav"].cummax()) / nav["nav"].cummax() * 100
    dr = nav["nav"].pct_change().dropna()
    import numpy as np
    sharpe = (dr.mean() * 252 - 0.02) / (dr.std() * np.sqrt(252)) if dr.std() > 0 else 0
    return {
        "preset": preset, "start": start, "end": end,
        "final_nav_x": round(final_nav / 1_000_000, 2),
        "cagr": round(cagr, 2), "sharpe": round(sharpe, 2),
        "max_dd": round(dd.min(), 2),
        "trade_count": ext.get("trade_count", 0),
        "commission": float(ext.get("total_commission", 0)),
    }


def run_parallel(jobs: list, max_workers: int = None, use_cache: bool = True):
    """
    Run multiple backtest jobs in parallel via ProcessPoolExecutor.

    jobs: list of dicts, each with {preset, start, end, execution_timing, config_override, universe_filter, preloaded}
    max_workers: None = min(cpu_count - 1, len(jobs))
    use_cache: skip jobs with cached results

    Returns list of result dicts (same order as input, None for failed).
    """
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor, as_completed

    n_jobs = len(jobs)
    if max_workers is None:
        max_workers = max(1, min(multiprocessing.cpu_count() - 1, n_jobs))

    results = [None] * n_jobs
    to_run = []

    for i, job in enumerate(jobs):
        if use_cache:
            key = cache_key(
                job["preset"], job["start"], job["end"],
                job.get("config_override"), job.get("universe_filter"),
                job.get("execution_timing", "next_open"),
            )
            cached = load_cached_result(key)
            if cached is not None:
                results[i] = cached
                continue
        to_run.append((i, job))

    if not to_run:
        return results

    t0 = time.time()
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {executor.submit(_run_one_backtest, job): idx for idx, job in to_run}
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                result = future.result(timeout=600)
                results[idx] = result
                # Write cache
                try:
                    job = jobs[idx]
                    key = cache_key(
                        job["preset"], job["start"], job["end"],
                        job.get("config_override"), job.get("universe_filter"),
                        job.get("execution_timing", "next_open"),
                    )
                    CACHE_DIR.mkdir(parents=True, exist_ok=True)
                    import json as _json
                    with open(CACHE_DIR / f"{key}.json", "w", encoding="utf-8") as f:
                        _json.dump(result, f, ensure_ascii=False)
                except Exception:
                    pass
            except Exception as e:
                print(f"  [Parallel] Job {idx} failed: {e}")

    elapsed = time.time() - t0
    print(f"  [Parallel] {len(to_run)} jobs in {elapsed:.1f}s ({max_workers} workers)")
    return results


# Global singleton
_GLOBAL_CACHE: Optional[BacktestDataCache] = None


def get_cache() -> BacktestDataCache:
    global _GLOBAL_CACHE
    if _GLOBAL_CACHE is None:
        _GLOBAL_CACHE = BacktestDataCache()
    return _GLOBAL_CACHE


# ============================================================
# Result cache
# ============================================================

def _param_hash(params: dict) -> str:
    """Stable hash for a param dict (keys sorted)."""
    raw = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def cache_key(preset: str, start: str, end: str, config_override: dict = None,
              universe_filter: list = None, execution_timing: str = "next_open") -> str:
    """Build a cache key for a backtest run."""
    parts = {
        "preset": preset,
        "start": start,
        "end": end,
        "execution_timing": execution_timing,
    }
    if config_override:
        parts["override_hash"] = _param_hash(config_override)
    if universe_filter:
        parts["universe_hash"] = _param_hash({"codes": sorted(universe_filter)})
    return _param_hash(parts)


def load_cached_result(key: str) -> Optional[dict]:
    """Load cached backtest result. Returns None if not found."""
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        import pandas as pd, json
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Convert back to DataFrames
        if "nav" in data:
            data["nav_df"] = pd.DataFrame(data.pop("nav"))
        return data
    except Exception:
        return None


def save_cached_result(key: str, nav_df, extra: dict):
    """Save backtest result to cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # Convert nav_df to dict for JSON
    nav_dict = nav_df.to_dict(orient="list")
    for col in nav_dict:
        if hasattr(nav_dict[col][0], "strftime"):
            nav_dict[col] = [v.strftime("%Y-%m-%d") if hasattr(v, "strftime") else str(v) for v in nav_dict[col]]
    data = {
        "nav": nav_dict,
        "summary": {
            "final_nav": float(nav_df["nav"].iloc[-1]),
            "days": len(nav_df),
        },
        "trade_count": extra.get("trade_count", 0),
        "total_commission": float(extra.get("total_commission", 0)),
        "cached_at": datetime.now().isoformat(),
    }
    with open(CACHE_DIR / f"{key}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
