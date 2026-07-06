"""Parameter layer definitions and utilities for layered optimization.

This module is the single source of truth for which params belong to which layer.
It is shared by iterative_optimizer.py and future optimization scripts.
"""

# ── Parameter layer key sets ──
# Signal layer: params that affect the composite score formula (ETF ranking)
SIGNAL_PARAM_KEYS = frozenset({
    'w1', 'w3', 'w7',
    'f1_sensitivity', 'f3_sensitivity',
    'f7_t', 'f7_k', 'f7_window',
    'f3_vol_window', 'f1_ema_period',
})

# Execution layer: params that affect position sizing and confidence filtering
EXECUTION_PARAM_KEYS = frozenset({
    'ma_bull_pos', 'ma_bear_pos', 'max_holdings',
    'ma_trend_period', 'concentration', 'c_sensitivity',
    'band', 'band_sensitivity', 'disc_step',
})

ALL_PARAM_KEYS = SIGNAL_PARAM_KEYS | EXECUTION_PARAM_KEYS


# ── Per-school defaults used when no best trial exists to pin from ──
# Mirrors INITIAL_PRESETS in quant_contract.py
SIGNAL_DEFAULTS = {
    'w1': 33, 'w3': 33, 'w7': 34,
    'f7_t': 10.0, 'f7_k': 3.0, 'f7_window': 20,
    'f3_vol_window': 30,
    'f1_sensitivity': 8.0, 'f3_sensitivity': 4.0,
    'f1_ema_period': 4,
}

EXECUTION_DEFAULTS = {
    'gambler': {'max_holdings': 4, 'ma_bear_pos': 0.50, 'ma_bull_pos': 1.0,
                'disc_step': 0.10, 'concentration': 3.0, 'c_sensitivity': 30,
                'band': 2.0, 'band_sensitivity': 0, 'ma_trend_period': 26},
    'zen':     {'max_holdings': 5, 'ma_bear_pos': 0.35, 'ma_bull_pos': 1.0,
                'disc_step': 0.08, 'concentration': 2.0, 'c_sensitivity': 15,
                'band': 1.5, 'band_sensitivity': 15, 'ma_trend_period': 30},
    'actuary': {'max_holdings': 4, 'ma_bear_pos': 0.25, 'ma_bull_pos': 0.80,
                'disc_step': 0.10, 'concentration': 4.0, 'c_sensitivity': 25,
                'band': 2.0, 'band_sensitivity': 25, 'ma_trend_period': 34},
}


def pin_params(best_trial, layer, school='gambler'):
    """Return {param_key: fixed_value} for the layer NOT being optimized.

    Args:
        best_trial: dict with 'params' key (the current best pool trial),
                    or None if no best trial exists
        layer: 'signal' or 'execution' — the layer BEING optimized
        school: 'gambler' | 'zen' | 'actuary' — for fallback defaults

    Returns:
        dict: fixed param values for the opposite layer
    """
    opposite_keys = EXECUTION_PARAM_KEYS if layer == 'signal' else SIGNAL_PARAM_KEYS

    if layer == 'signal':
        fallback = EXECUTION_DEFAULTS.get(school[:3], EXECUTION_DEFAULTS['gambler'])
    else:
        fallback = SIGNAL_DEFAULTS

    pinned = {}
    for k in opposite_keys:
        if best_trial and k in best_trial.get('params', {}):
            pinned[k] = best_trial['params'][k]
        elif k in fallback:
            pinned[k] = fallback[k]
    return pinned


def normalize_weights(params):
    """Ensure w1 + w3 + w7 == 100 after crossover/mutation.

    If sum is 0 or negative, uses SIGNAL_DEFAULTS.
    Modifies params dict in-place.
    """
    w1 = params.get('w1', 0)
    w3 = params.get('w3', 0)
    w7 = params.get('w7', 0)
    total = int(w1) + int(w3) + int(w7)
    if total <= 0:
        params['w1'] = SIGNAL_DEFAULTS['w1']
        params['w3'] = SIGNAL_DEFAULTS['w3']
        params['w7'] = SIGNAL_DEFAULTS['w7']
    elif total != 100:
        scale = 100.0 / total
        params['w1'] = int(round(w1 * scale))
        params['w3'] = int(round(w3 * scale))
        params['w7'] = 100 - params['w1'] - params['w3']


def layer_keys(layer):
    """Return the param key set for the given layer."""
    if layer == 'signal':
        return SIGNAL_PARAM_KEYS
    elif layer == 'execution':
        return EXECUTION_PARAM_KEYS
    else:
        return ALL_PARAM_KEYS
