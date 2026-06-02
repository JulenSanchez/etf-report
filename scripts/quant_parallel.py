"""Multiprocessing backtest runner for parallel window/persona verification.
Usage:
    from quant_parallel import parallel_backtests
    jobs = [{"preset":"preset1","start":"2025-05-28","end":"2026-05-27"}, ...]
    results = parallel_backtests(jobs)  # 4 workers by default
"""
import os, sys, io
from contextlib import redirect_stdout, redirect_stderr
from concurrent.futures import ProcessPoolExecutor, as_completed


def _worker(job):
    """Single backtest in a subprocess. Suppress stdout to avoid interleaving."""
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from quant_backtest import run_backtest as _run
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        nav_df, signal_history, extra = _run(
            start_date=job["start"],
            end_date=job["end"],
            preset=job["preset"],
            config_override=job.get("config_override"),
            execution_timing=job.get("execution_timing", "same_close"),
            return_details=True,
        )
    return nav_df, signal_history, extra


def parallel_backtests(jobs, max_workers=None):
    """Run multiple independent backtests in parallel subprocesses.

    Args:
        jobs: list of dicts, each with keys: preset, start, end
              Optional: config_override, execution_timing
        max_workers: number of parallel processes (default: min(4, len(jobs)))

    Returns:
        list of (nav_df, signal_history, extra) tuples, same order as jobs.
        Failed jobs return (None, None, None).
    """
    if not jobs:
        return []

    n = max_workers or min(4, len(jobs))
    results = [None] * len(jobs)

    with ProcessPoolExecutor(max_workers=n) as pool:
        futures = {}
        for i, job in enumerate(jobs):
            fut = pool.submit(_worker, job)
            futures[fut] = i

        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                results[idx] = fut.result()
            except Exception as e:
                print(f"[parallel] job {idx} failed: {e}")
                results[idx] = (None, None, None)

    return results
