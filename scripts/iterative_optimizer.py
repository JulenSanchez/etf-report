#!/usr/bin/env python3
"""迭代缩界 TPE — 自适应 pool.json 驱动。

池子行为:
  < 5 条 valid → 冷启动: YAML 预设 → [不够] Sobol → [不够] TPE 全界
  >= 5 条 → 正常迭代: narrow_bounds → TPE → merge → prune → save (每轮)
  每轮结束立刻 prune，池子永不膨胀。

一个 school 一个进程。不同 school 可并行（独立 pool）。
"""
import sys, json, pathlib, argparse, warnings, random
# Suppress optuna distribution alignment warnings — we snap bounds to step already
warnings.filterwarnings('ignore', message='The distribution is specified by')
warnings.filterwarnings('ignore', message='Fixed parameter')
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from etf_report.core.quant_contract import (
    tuner_params_to_config_override, create_optuna_objective,
    narrow_bounds_from_trials, PARAM_BOUNDS,
    load_pool, save_pool, prune_pool, seed_params_from_presets,
)
from resolved_params import (
    SIGNAL_PARAM_KEYS, EXECUTION_PARAM_KEYS, ALL_PARAM_KEYS,
    pin_params, normalize_weights, layer_keys,
)
from pareto_optimizer import crossover_params
import optuna


def load_all_trials(pool_dir):
    """Load all trials from a directory tree of JSON files, deduplicated by (mdd, composite)."""
    import pathlib
    root = pathlib.Path(pool_dir)
    if not root.exists():
        return []
    seen = set()
    results = []
    for fpath in sorted(root.rglob("*.json")):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            mdd = item.get("mdd")
            comp = item.get("composite")
            if mdd is None or comp is None:
                continue
            key = (round(float(mdd), 4), round(float(comp), 4))
            if key not in seen:
                seen.add(key)
                results.append(item)
    return results


def _valid(trials):
    return [t for t in trials if t.get('mdd') is not None and t.get('composite') is not None]


def _run_trials(preset, bounds, start_date, end_date, metric, n, label, seed=42,
                sampler='tpe', enqueue_seeds=None, recovery_path=None, pinned_params=None):
    s = optuna.samplers.QMCSampler(seed=seed) if sampler == 'sobol' \
        else optuna.samplers.TPESampler(seed=seed)
    # Merge pinned params into bounds with fixed (value, value, 1) so the
    # objective function always samples the full 19-param set.
    _active_bounds = dict(bounds)
    if pinned_params:
        for k, v in pinned_params.items():
            _active_bounds[k] = (v, v, 1)  # fixed = no search freedom
    obj = create_optuna_objective(preset, _active_bounds, start_date, end_date, metric)
    study = optuna.create_study(direction='maximize', sampler=s)
    if enqueue_seeds:
        # Expand bounds to cover seed values (avoid "Fixed parameter out of range" warnings)
        for sp in enqueue_seeds:
            for k, v in sp.items():
                if k in bounds:
                    lo, hi, step = bounds[k]
                    if v < lo:
                        bounds[k] = (v, hi, step)
                    elif v > hi:
                        bounds[k] = (lo, v, step)
        for sp in enqueue_seeds:
            try: study.enqueue_trial(sp)
            except Exception: pass

    # ── Incremental save: flush partial results to recovery file every 10 trials ──
    callbacks = []
    if recovery_path:
        _rp = pathlib.Path(recovery_path)
        def _save_recovery(study, trial):
            if trial.number > 0 and trial.number % 10 == 0:
                partial = []
                for t in study.trials:
                    if t.value is not None and t.value > -9000:
                        md = t.user_attrs.get('mdd', -99)
                        if -40 <= md <= -20:
                            partial.append({
                                'mdd': md,
                                'composite': t.user_attrs['composite'],
                                'params': json.loads(t.user_attrs.get('params', '{}')),
                                'source': label,
                            })
                if partial:
                    try:
                        _rp.parent.mkdir(parents=True, exist_ok=True)
                        _rp.write_text(json.dumps(partial, ensure_ascii=False, indent=1),
                                       encoding='utf-8')
                    except Exception:
                        pass  # never crash the optimize loop for recovery IO
        callbacks.append(_save_recovery)

    study.optimize(obj, n_trials=n, n_jobs=1, show_progress_bar=(n >= 20),
                   callbacks=callbacks or None)

    # ── Clean up recovery file on successful completion ──
    if recovery_path:
        _rp = pathlib.Path(recovery_path)
        if _rp.exists():
            try: _rp.unlink()
            except Exception: pass

    results = []
    dropped = 0
    for t in study.trials:
        if t.value is not None and t.value > -9000:
            md = t.user_attrs.get('mdd', -99)
            if md < -40 or md > -20:
                dropped += 1   # out of target range — discard immediately
                continue
            results.append({
                'mdd': md,
                'composite': t.user_attrs['composite'],
                'params': json.loads(t.user_attrs.get('params', '{}')),
                'source': label,
            })
    if dropped > 0:
        print(f'  [{label}] {dropped} trials out of [-40,-20] range — discarded')
    return results


def _validate_seeds(pool, preset, start_date, end_date, metric, max_n=20):
    """Run backtests on unvalidated pool entries to fill MDD/COMP."""
    from quant_backtest import run_backtest as _rb
    seeds = [t for t in pool if t.get('mdd') is None and t.get('params')]
    if not seeds:
        return pool
    n = min(len(seeds), max_n)
    print(f'Validating {n} seed entries ...')
    count = 0
    for t in seeds[:n]:
        p = t['params']
        try:
            ov = tuner_params_to_config_override(p)
            nav, _, extra = _rb(start_date=start_date, end_date=end_date,
                                preset=preset, config_override=ov, return_data=False)
            if nav is not None and len(nav) >= 2:
                days = (nav['date'].iloc[-1] - nav['date'].iloc[0]).days
                if days > 0:
                    t['mdd'] = round(((nav['nav'] - nav['nav'].cummax()) / nav['nav'].cummax() * 100).min(), 2)
                    if metric == '6y_sortino':
                        t['composite'] = round(extra.get('sortino', 0), 4)
                    else:
                        ar = (nav['nav'].iloc[-1] / nav['nav'].iloc[0]) ** (365.0 / days) - 1
                        t['composite'] = round(ar * 100, 2)
                    count += 1
        except Exception:
            continue
    print(f'  {count}/{n} seeds validated')
    return pool


def _frontier_seeds(school, pool_dir='research/params'):
    """Extract params from frontier_{school}.json as seed entries."""
    fp = pathlib.Path(pool_dir) / f'frontier_{school}.json'
    if not fp.exists():
        return []
    try:
        data = json.loads(fp.read_text('utf-8'))
        points = data.get(school, {}).get('points', [])
        seeds = []
        for pt in points:
            if 'params' in pt:
                # Drop placeholder mdd/ar from frontier format
                p = dict(pt['params'])
                seeds.append({'params': p, 'source': 'frontier'})
        return seeds
    except Exception:
        return []


def _cross_frontier_seeds(school, pool_dir='research/params'):
    """Extract frontier params from ALL OTHER schools for cross-pollination."""
    other_schools = {'gambler', 'zen', 'actuary'} - {school}
    seeds = []
    for other in other_schools:
        for pt in _frontier_seeds(other, pool_dir):
            pt['source'] = f'cross:{other}'
            seeds.append(pt)
    return seeds


def _sobol_random_seeds(n, seed=42, label='sobol'):
    """Generate n random param sets using full bounds (no backtest)."""
    import optuna as _optuna
    fb = _full_bounds()
    if not fb:
        return []
    sampler = _optuna.samplers.QMCSampler(seed=seed)
    study = _optuna.create_study(direction='maximize', sampler=sampler)
    study.optimize(lambda t: 0.0, n_trials=n, n_jobs=1)
    seeds = []
    for t in study.trials:
        p = {}
        for k, (lo, hi, step) in fb.items():
            if isinstance(step, int) or (isinstance(step, float) and step == int(step)):
                p[k] = int(t.suggest_float(k, lo, hi, step=int(step)))
            else:
                p[k] = t.suggest_float(k, lo, hi, step=step)
        normalize_weights(p)
        seeds.append({'params': p, 'source': label})
    return seeds


def _crossover_seeds(pool, n, label='crossover'):
    """Generate n crossover children from existing pool trials."""
    if len(pool) < 2:
        return []
    valid = [t for t in pool if t.get('params')]
    if len(valid) < 2:
        return []
    seeds = []
    for i in range(n):
        p1 = random.choice(valid)['params']
        p2 = random.choice(valid)['params']
        child = crossover_params(p1, p2)
        normalize_weights(child)
        seeds.append({'params': child, 'source': label})
    return seeds


def generate_multi_seeds(school, sources='all', n_sobol=30, n_crossover=10,
                          pool_dir='research/params', existing_pool=None):
    """Generate seed trials from multiple sources in parallel.

    Args:
        school: 'gambler' | 'zen' | 'actuary'
        sources: comma-separated list or 'all'
        n_sobol: number of Sobol QMC random seeds
        n_crossover: number of crossover children
        pool_dir: directory for frontier files
        existing_pool: optional list of existing trial dicts (for crossover)

    Returns:
        list of seed dicts [{params: {...}, source: '...'}]
    """
    if sources == 'all':
        source_list = ['presets', 'frontier', 'cross-frontier', 'sobol', 'crossover']
    else:
        source_list = [s.strip() for s in sources.split(',')]

    seeds = []
    for src in source_list:
        if src == 'presets':
            generated = seed_params_from_presets(school)
        elif src == 'frontier':
            generated = _frontier_seeds(school, pool_dir)
        elif src == 'cross-frontier':
            generated = _cross_frontier_seeds(school, pool_dir)
        elif src == 'sobol':
            seed_offset = hash(school) % 10000
            generated = _sobol_random_seeds(n_sobol, seed=42 + seed_offset, label='sobol')
        elif src == 'crossover':
            generated = _crossover_seeds(existing_pool or [], n_crossover, label='crossover')
        else:
            print(f'  [WARN] Unknown seed source: {src}')
            continue
        if generated:
            print(f'  [{src}] -> {len(generated)} seeds')
            seeds.extend(generated)

    # Deduplicate by params hash
    seen, unique = set(), []
    for s in seeds:
        h = json.dumps(s.get('params', {}), sort_keys=True)
        if h not in seen:
            seen.add(h)
            unique.append(s)
    if len(unique) < len(seeds):
        print(f'  Dedup: {len(seeds)} -> {len(unique)} unique')
    return unique


def _full_bounds():
    b = {}
    for k, v in PARAM_BOUNDS.items():
        if v.get('type') in ('weight', 'continuous', 'integer') and v.get('searchable', True):
            b[k] = (v['min'], v['max'], v.get('step', 1))
    return b


# ═══════════════════════════════════════════════════════════════════════════
# Multi-zone parallel workers (REQ-344) — must be module-level for spawn
# ═══════════════════════════════════════════════════════════════════════════

_ZONE_RANGES = {'A': (-40, -35), 'B': (-35, -30), 'C': (-30, -25), 'D': (-25, -20)}
_ZONE_SEED_OFFSETS = {'A': 0, 'B': 100, 'C': 200, 'D': 300}
ZONE_ORDER = ['A', 'B', 'C', 'D']


def _run_zone_round(pool_snapshot, zone_label, zone_range, preset,
                    start_date, end_date, metric, n_trials, seed,
                    top_n, bounds_margin, bounds_band, pool_dir=None,
                    pinned_params=None, active_keys=None):
    """Top-level worker for --multi-zone parallel execution. Must be picklable.

    Runs one round of TPE optimized for a single 5% MDD zone.

    Returns:
        list of new trial dicts whose MDD is strictly inside zone_range.
    """
    zlo, zhi = zone_range

    # ── Filter pool to this zone ──
    zone_trials = [t for t in pool_snapshot
                   if t.get('mdd') is not None and zlo <= t['mdd'] < zhi]

    # ── Narrow bounds from zone-only trials ──
    if len(zone_trials) >= 3:
        _bw = bounds_band if bounds_band > 0 else None
        bounds = narrow_bounds_from_trials(
            zone_trials, top_n, margin_pct=bounds_margin, band_width=_bw,
            param_keys=active_keys)
        if not bounds:
            bounds = _full_bounds()
    else:
        bounds = _full_bounds()
    # Filter to active layer
    if active_keys:
        bounds = {k: v for k, v in bounds.items() if k in active_keys}

    _active_count = len(bounds)
    if pinned_params:
        _active_count = len(bounds)
    print(f'  [Zone {zone_label}] {len(zone_trials)} zone trials, '
          f'{_active_count} narrowed params')

    # ── TPE run ──
    _rec_path = str(pathlib.Path(pool_dir) / f'.recovery_mz_{zone_label.lower()}.json') if pool_dir else None
    new_trials = _run_trials(preset, bounds, start_date, end_date,
                             metric, n_trials, f'mz_{zone_label}',
                             seed=seed, recovery_path=_rec_path,
                             pinned_params=pinned_params)

    # ── Filter to this zone's exact MDD range (out-of-zone trials go to shared pool via merge) ──
    zone_new = [t for t in new_trials
                if t.get('mdd') is not None and zlo <= t['mdd'] < zhi]

    out_of_zone = len(new_trials) - len(zone_new)
    if out_of_zone > 0:
        print(f'  [Zone {zone_label}] {out_of_zone} trials outside [{zlo},{zhi}) '
              f'-- available for other zones in shared pool')

    return zone_new


def _print_multi_zone_status(round_num, max_rounds, zone_active, zone_results,
                             pool_size, metric_label):
    """Print per-round multi-zone status line."""
    active_labels = [z for z, active in zone_active.items() if active]
    parts = []
    for label in active_labels:
        new = zone_results.get(label, [])
        if new:
            best = max((r['composite'] for r in new), default=0)
            parts.append(f"{label}={best:.1f}")
        else:
            parts.append(f"{label}=--")
    print(f'\n=== Round {round_num}/{max_rounds}: '
          f'Pool={pool_size} | {"  ".join(parts)} ===')


def main():
    p = argparse.ArgumentParser(description='迭代缩界 TPE — 自适应 pool')
    p.add_argument('--school', required=True, choices=['gambler', 'zen', 'actuary'])
    p.add_argument('--zone', default=None, choices=['A','B','C','D'],
                   help='单区模式: A=[-40,-35) B=[-35,-30) C=[-30,-25) D=[-25,-20)')
    p.add_argument('--multi-zone', action='store_true',
                   help='四区并行模式: A/B/C/D 各独立 TPE, 并行优化 (与 --zone 互斥)')
    p.add_argument('--max-concurrent', type=int, default=4, choices=range(1, 5),
                   help='最大并行区数 (default: 4)')
    p.add_argument('--top-n', type=int, default=15,
                   help='缩界用 top-N trial (default: 15)')
    p.add_argument('--trials-per-round', type=int, default=30)
    p.add_argument('--max-rounds', type=int, default=5)
    p.add_argument('--cold-trials', type=int, default=50,
                   help='冷启动 Sobol trial 数 (default: 50)')
    p.add_argument('--preset', default=None)
    p.add_argument('--target-metric', default=None,
                   choices=['6y_ar', '3y_ar', '6y_sortino', '6y_calmar'])
    p.add_argument('--start-date', default='2020-06-25')
    p.add_argument('--end-date', default=None)
    p.add_argument('--pool-dir', default='research/params')
    p.add_argument('--seed', type=int, default=42)
    # ── TPE 收敛突破 (REQ-335) ──
    p.add_argument('--sobol-every', type=int, default=0,
                   help='每 N 轮插入 Sobol 注入多样性 (0=关闭)')
    p.add_argument('--bounds-margin', type=float, default=0.3,
                   help='窄界松弛系数 (default: 0.3, 调大=更宽探索)')
    p.add_argument('--bounds-band', type=float, default=5,
                   help='Band width in pct, 0=global top-N (default: 5)')
    p.add_argument('--fill-slots', action='store_true',
                   help='Auto-fill MDD slots until full coverage')
    p.add_argument('--output', default=None,
                   help='Extra output file for multi-seed parallel runs')
    # ── Prune tuning ──
    p.add_argument('--prune-band', type=float, default=None,
                   help='MDD slot width (default: 1.0)')
    p.add_argument('--prune-per-band', type=int, default=None,
                   help='每槽位保留数 (default: 1)')
    p.add_argument('--frontier', action='store_true',
                   help='优化完成后自动重建前沿文件')
    p.add_argument('--layer', choices=['signal', 'execution', 'all'], default='all',
                   help='Optimization layer: signal (10 params) | execution (9 params) | all (default)')
    p.add_argument('--seed-sources', default=None,
                   help='Multi-source seeds: all | presets,frontier,cross-frontier,sobol,crossover')
    p.add_argument('--n-sobol', type=int, default=30,
                   help='Number of Sobol random seeds (default: 30)')
    p.add_argument('--n-crossover', type=int, default=10,
                   help='Number of crossover children (default: 10)')
    args = p.parse_args()

    if args.multi_zone and args.zone:
        p.error('--multi-zone and --zone are mutually exclusive')

    _DF = {
        'gambler': {'preset': 'gam-2', 'metric': '6y_ar',
                    'prune_band': 1.0, 'prune_per_band': 1},
        'zen':     {'preset': 'zen-1', 'metric': '6y_sortino',
                    'prune_band': 1.0, 'prune_per_band': 1},
        'actuary': {'preset': 'act-1', 'metric': '6y_calmar',
                    'prune_band': 1.0, 'prune_per_band': 1},
    }
    df = _DF[args.school]
    preset = args.preset or df['preset']
    metric = args.target_metric or df['metric']
    prune_kw = {
        'band': args.prune_band if args.prune_band is not None else df['prune_band'],
        'per_band': args.prune_per_band if args.prune_per_band is not None else df['prune_per_band'],
    }

    # ── Load pool ──
    pool = load_pool(args.school, args.pool_dir)
    n_valid = len(_valid(pool))
    n_seeds = len([t for t in pool if t.get('mdd') is None])
    # Backfill new params (B/BS) into old pool trials with slight random jitter
    # to ensure narrow_bounds has a non-degenerate range for these params.
    import random as _random
    _backfilled = 0
    for _ti, t in enumerate(pool):
        p = t.get('params', {})
        if 'band' not in p:
            p['band'] = round(2.0 + _random.random() * 2.0, 1)  # [2.0, 4.0]
            _backfilled += 1
        if 'band_sensitivity' not in p:
            p['band_sensitivity'] = _random.randint(0, 50)  # [0, 50]
            _backfilled += 1
    if _backfilled:
        print(f'  Backfilled {_backfilled} missing B/BS params in pool')
        save_pool(args.school, pool, args.pool_dir)
    print(f'Loaded {len(pool)} entries, {n_valid} valid, {n_seeds} unvalidated')

    # ── Recover partial results from previous crashed run ──
    import glob as _glob
    _recovery_patterns = [
        str(pathlib.Path(args.pool_dir) / f".recovery_{args.school}_*.json"),
        str(pathlib.Path(args.pool_dir) / f".recovery_mz_*.json"),
    ]
    _any_recovered = False
    for _pat in _recovery_patterns:
        for _rf in sorted(_glob.glob(_pat)):
            try:
                _rec = json.loads(pathlib.Path(_rf).read_text('utf-8'))
                if isinstance(_rec, list) and _rec:
                    pool.extend(_rec)
                    print(f'  Recovered {len(_rec)} trials from {pathlib.Path(_rf).name}')
                    pathlib.Path(_rf).unlink()
                    _any_recovered = True
            except Exception:
                pass
    if _any_recovered:
        n_valid = len(_valid(pool))
        print(f'  After recovery: {len(pool)} entries, {n_valid} valid')

    # ── Always validate seeds (fill MDD/COMP so they participate in search) ──
    if n_seeds > 0:
        pool = _validate_seeds(pool, preset, args.start_date, args.end_date, metric)
        n_valid = len(_valid(pool))

    # ── Zone mode: filter pool to this zone, set output path ──
    _ZONE_RANGES = {'A': (-40, -35), 'B': (-35, -30), 'C': (-30, -25), 'D': (-25, -20)}
    if args.zone:
        zlo, zhi = _ZONE_RANGES[args.zone]
        pool = [t for t in pool if t.get('mdd') is None or (zlo <= t['mdd'] < zhi)]
        if not args.output:
            args.output = f'research/params/runs/{args.school}_{args.zone}.json'
        print(f'Zone {args.zone}: MDD [{zlo},{zhi}), {len(pool)} entries')
        if not pool:
            print('Zone pool empty — cold starting with YAML seeds')
            pool = seed_params_from_presets(args.school) or []

    # ══════════════════════════════════════════════════════════════
    # Self-seeding: multi-source parallel injection (cold-start) or
    # warm-start crossover injection
    # ══════════════════════════════════════════════════════════════
    _seed_sources = args.seed_sources
    if n_valid < 5 and not _seed_sources:
        _seed_sources = 'all'  # default for cold-start

    if n_valid < 5:
        print(f'\n=== Pool sparse — multi-source seed injection ({_seed_sources}) ===')

        # Parallel injection from all sources
        seeds = generate_multi_seeds(
            school=args.school, sources=_seed_sources,
            n_sobol=args.n_sobol, n_crossover=args.n_crossover,
            pool_dir=args.pool_dir, existing_pool=pool,
        )
        if seeds:
            pool.extend(seeds)
            print(f'  Total: {len(seeds)} seeds injected (unvalidated)')
            n_seeds = len([t for t in pool if t.get('mdd') is None])
            pool = _validate_seeds(pool, preset, args.start_date, args.end_date, metric)
            n_valid = len(_valid(pool))
            print(f'  After validation: {n_valid} valid')

        # Fallback: if still insufficient, run Sobol + TPE full bounds
        if len(_valid(pool)) < 5:
            fb = _full_bounds()
            n = max(args.cold_trials, 20)
            new_t = _run_trials(preset, fb, args.start_date, args.end_date,
                               metric, n, 'sobol_fallback', seed=args.seed, sampler='sobol')
            pool.extend(new_t)
            before = len(pool)
            pool = prune_pool(pool, args.school, **prune_kw)
            print(f'  Sobol fallback {n} -> {len(new_t)} ok -> prune {before}->{len(pool)}')
            save_pool(args.school, pool, args.pool_dir)

        if len(_valid(pool)) < 3:
            fb = _full_bounds()
            new_t = _run_trials(preset, fb, args.start_date, args.end_date,
                               metric, 30, 'tpe_full', seed=args.seed + 1)
            pool.extend(new_t)
            before = len(pool)
            pool = prune_pool(pool, args.school, **prune_kw)
            print(f'  TPE full 30 -> {len(new_t)} ok -> prune {before}->{len(pool)}')
            save_pool(args.school, pool, args.pool_dir)

    # ══════════════════════════════════════════════════════════════
    # Phase 2 dispatch: multi-zone parallel (REQ-344) or classic iterative TPE
    # ══════════════════════════════════════════════════════════════
    if args.multi_zone:
        # ── Multi-zone parallel TPE ──
        import concurrent.futures

        zone_active = {z: True for z in ZONE_ORDER}
        zone_stale  = {z: 0 for z in ZONE_ORDER}
        zone_prev_best = {z: -999.0 for z in ZONE_ORDER}
        zone_results = {}
        _metric_label = {'6y_ar': 'AR', '3y_ar': 'AR', '6y_sortino': 'Sortino', '6y_calmar': 'Calmar'}.get(metric, 'COMP')

        # ── Layer-aware setup for multi-zone ──
        _mz_active_keys = layer_keys(args.layer) if args.layer != 'all' else None
        _mz_pinned = None
        if args.layer != 'all' and pool:
            _v = _valid(pool)
            if _v:
                _best = max(_v, key=lambda r: r.get('composite', -999))
                _mz_pinned = pin_params(_best, args.layer, args.school)

        for outer_round in range(1, args.max_rounds + 1):
            active = [z for z in ZONE_ORDER if zone_active[z]]
            if not active:
                print('\nAll zones converged.')
                break

            _print_multi_zone_status(outer_round, args.max_rounds,
                                     zone_active, zone_results, len(pool),
                                     _metric_label)

            pool_snapshot = list(pool)
            zone_results = {}

            n_workers = min(args.max_concurrent, len(active))
            with concurrent.futures.ProcessPoolExecutor(max_workers=n_workers) as ex:
                futures = {}
                for label in active:
                    zlo, zhi = _ZONE_RANGES[label]
                    seed_val = args.seed + _ZONE_SEED_OFFSETS[label] + outer_round * 10
                    fut = ex.submit(
                        _run_zone_round,
                        pool_snapshot, label, (zlo, zhi),
                        preset, args.start_date, args.end_date, metric,
                        args.trials_per_round, seed_val,
                        args.top_n, args.bounds_margin, args.bounds_band,
                        args.pool_dir,
                        _mz_pinned, _mz_active_keys,
                    )
                    futures[fut] = label

                for fut in concurrent.futures.as_completed(futures):
                    label = futures[fut]
                    try:
                        zone_results[label] = fut.result()
                    except Exception as e:
                        print(f'  [Zone {label}] CRASHED: {e}')
                        import traceback
                        traceback.print_exc()
                        zone_results[label] = []
                        zone_active[label] = False

            # ── Merge + prune ──
            total_new = 0
            for label in ZONE_ORDER:
                new_trials = zone_results.get(label, [])
                if not new_trials:
                    continue
                pool.extend(new_trials)
                total_new += len(new_trials)

                # Per-zone convergence
                round_best = max((r['composite'] for r in new_trials), default=-999)
                prev = zone_prev_best[label]
                if prev > -900 and abs(prev) > 0.01:
                    improvement = (round_best - prev) / abs(prev) * 100
                else:
                    improvement = 100
                zone_prev_best[label] = max(prev, round_best)

                if abs(improvement) < 2:
                    zone_stale[label] += 1
                    if zone_stale[label] >= 2:
                        zone_active[label] = False
                        print(f'  Zone {label}: converged ({zone_stale[label]} '
                              f'stale rounds, best={round_best:.1f})')
                else:
                    zone_stale[label] = 0

            before = len(pool)
            pool = prune_pool(pool, args.school, **prune_kw)
            save_pool(args.school, pool, args.pool_dir)
            print(f'  Prune: {before}->{len(pool)} (+{total_new} new, dropped {before + total_new - len(pool)})')

            # ── Write per-zone output files ──
            out_base = pathlib.Path(args.pool_dir) / 'runs'
            out_base.mkdir(parents=True, exist_ok=True)
            for label in ZONE_ORDER:
                new_trials = zone_results.get(label, [])
                if new_trials:
                    out_f = out_base / f'{args.school}_{label}.json'
                    out_f.write_text(json.dumps(new_trials, ensure_ascii=False, indent=1),
                                     encoding='utf-8')

    else:
        # ══════════════════════════════════════════════════════════════
        # Phase 2: Iterative TPE — batches with optional slot fill
        # ══════════════════════════════════════════════════════════════
        max_batches = 5 if args.fill_slots else 1
        prev_slots = 0
        stale_batches = 0

        for batch in range(1, max_batches + 1):
            if args.fill_slots:
                print(f'\n=== Batch {batch}/{max_batches} ===')

            prev_best = -999
            stale_count = 0

            for rnd in range(1, args.max_rounds + 1):
                v = _valid(pool)
                top = max((r['composite'] for r in v), default=0)
                mdds = [r['mdd'] for r in v]
                _metric_label = {'6y_ar': 'AR', '3y_ar': 'AR', '6y_sortino': 'Sortino', '6y_calmar': 'Calmar'}.get(metric, 'COMP')
                if v:
                    print(f'\n=== Round {rnd}: {len(v)} valid, '
                          f'MDD [{min(mdds):.1f}%, {max(mdds):.1f}%], top {_metric_label}={top:.1f} ===')
                else:
                    print(f'\n=== Round {rnd}: 0 valid, cold starting with full bounds ===')

                _bw = args.bounds_band if args.bounds_band > 0 else None

                # ── Layer-aware bounds ──
                _active_keys = layer_keys(args.layer) if args.layer != 'all' else None
                bounds = narrow_bounds_from_trials(v, args.top_n, margin_pct=args.bounds_margin,
                                                   band_width=_bw, param_keys=_active_keys) if len(v) >= 3 else _full_bounds()
                # Filter bounds to active layer if layered mode
                if _active_keys:
                    bounds = {k: v for k, v in bounds.items() if k in _active_keys}

                # Backfill missing or degenerate params from PARAM_BOUNDS (only active layer)
                for _k, _v in PARAM_BOUNDS.items():
                    if _v.get("type") in ("weight", "special", "categorical"):
                        continue
                    if not _v.get("searchable", True):
                        continue
                    if _active_keys and _k not in _active_keys:
                        continue
                    if _k not in bounds or bounds[_k][0] == bounds[_k][1]:  # missing or degenerate
                        bounds[_k] = (_v["min"], _v["max"], _v["step"])

                # ── Pinned params (opposite layer fixed to best trial) ──
                pinned = None
                if args.layer != 'all' and v:
                    best = max(v, key=lambda r: r.get('composite', -999))
                    pinned = pin_params(best, args.layer, args.school)
                    print(f'  Layer: {args.layer} ({len(bounds)} params), '
                          f'{len(pinned)} pinned from best trial')
                print(f'  Bounds: {len(bounds)} params (margin={args.bounds_margin}, band={args.bounds_band})')

                if args.sobol_every > 0 and rnd % args.sobol_every == 0:
                    print(f'  [Sobol inject] {args.trials_per_round} trials with full bounds')
                    fb = _full_bounds()
                    if _active_keys:
                        fb = {k: v for k, v in fb.items() if k in _active_keys}
                    sobol_inject = _run_trials(preset, fb, args.start_date, args.end_date,
                                               metric, args.trials_per_round, f'sobol_r{rnd}',
                                               seed=args.seed + rnd + 9999, sampler='sobol',
                                               pinned_params=pinned)
                    pool.extend(sobol_inject)
                    pool = prune_pool(pool, args.school, **prune_kw)
                    save_pool(args.school, pool, args.pool_dir)
                    print(f'  Sobol inject: {len(sobol_inject)} new → pool={len(pool)}')
                    continue

                seed_params = [t['params'] for t in v[:5] if t.get('params')]
                # ── Warm-start crossover injection ──
                if args.seed_sources and 'crossover' in args.seed_sources:
                    _cross = _crossover_seeds(pool, args.n_crossover)
                    if _cross:
                        seed_params = list(seed_params)
                        seed_params.extend([s['params'] for s in _cross])
                _rec_path = str(pathlib.Path(args.pool_dir) / f".recovery_{args.school}_iter_r{rnd}.json")
                new_trials = _run_trials(preset, bounds, args.start_date, args.end_date,
                                         metric, args.trials_per_round, f'iter_r{rnd}',
                                         seed=args.seed + rnd, enqueue_seeds=seed_params,
                                         recovery_path=_rec_path, pinned_params=pinned)
                pool.extend(new_trials)
                before = len(pool)
                pool = prune_pool(pool, args.school, **prune_kw)
                print(f'  {len(new_trials)} new → prune {before}→{len(pool)} (dropped {before - len(pool)})')

                round_best = max((r['composite'] for r in new_trials), default=0)
                improvement = (round_best - prev_best) / abs(prev_best) * 100 if prev_best > 0 else 100
                print(f'  Best new {_metric_label}={round_best:.1f} (+{improvement:+.1f}%)')

                save_pool(args.school, pool, args.pool_dir)

                if abs(improvement) < 2:
                    stale_count += 1
                    if stale_count >= 2:
                        print(f'\nConverged after {rnd} rounds')
                        break
                else:
                    stale_count = 0
                prev_best = max(prev_best, round_best)

            # ── Batch-level frontier slot check ──
            if args.fill_slots:
                from etf_report.core.quant_contract import compute_frontier
                f = compute_frontier(_valid(pool), mdd_range=(-40, -20))
                filled = set(int(round(t['mdd'])) for t in f)
                slot_count = len(filled)
                if slot_count >= 21:
                    print(f'\nAll 21 frontier slots filled after batch {batch}')
                    break
                if slot_count > prev_slots:
                    prev_slots = slot_count
                    stale_batches = 0
                else:
                    stale_batches += 1
                    if stale_batches >= 2:
                        missing = sorted(set(range(-40, -19)) - filled)
                        print(f'\nNo new slots for 2 batches. Filled: {slot_count}/21, missing: {missing}')
                        break
                print(f'  Batch {batch}: frontier slots {slot_count}/21')

    # ── Final ──
    vf = _valid(pool)
    if vf:
        mdds = [r['mdd'] for r in vf]
        best = max(vf, key=lambda r: r['composite'])
        _metric_label2 = _metric_label
        print(f'\nFinal: {len(pool)} entries, MDD [{min(mdds):.1f}%, {max(mdds):.1f}%], '
              f'best {_metric_label2}={best["composite"]:.1f} @ MDD={best["mdd"]:.1f}%')
    if args.output:
        out = pathlib.Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(pool, ensure_ascii=False, indent=1))
        print(f'Wrote {out}')
    print('Done.')

    if args.frontier:
        print(f'\n=== Building frontier for {args.school} ===')
        from etf_report.core.quant_contract import build_frontier_output
        result = build_frontier_output(school=args.school, start_date=args.start_date)
        print(f'Frontier: {result["points"]} points')


if __name__ == '__main__':
    main()
