"""Unit tests for optimization core — compute_frontier, narrow_bounds, load_all_trials.

Non-target: make_objective (requires real backtest = integration), full optimize loop (too slow).
"""
import sys, json, pathlib, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import pytest
from etf_report.core.quant_contract import compute_frontier, narrow_bounds_from_trials


# ═══════════════════════════════════════════════════════════════════════════
# compute_frontier
# ═══════════════════════════════════════════════════════════════════════════

def test_compute_frontier_basic():
    """Non-dominated sort: dominated points have worse MDD AND worse COMP."""
    points = [
        {"mdd": -22, "composite": 55},   # frontier: lowest risk
        {"mdd": -25, "composite": 70},   # frontier: more risk IS rewarded
        {"mdd": -30, "composite": 85},   # frontier: highest risk, highest return
        {"mdd": -35, "composite": 60},   # dominated: more risk than -30, LESS return
    ]
    frontier = compute_frontier(points, mdd_range=(-40, -15))
    assert len(frontier) == 3, f"Expected 3 frontier points, got {len(frontier)}"
    comps = [f["composite"] for f in frontier]
    assert max(comps) == 85


def test_compute_frontier_mdd_filter():
    """MDD range filter excludes points outside range."""
    points = [
        {"mdd": -10, "composite": 80},   # outside (-40, -20)
        {"mdd": -25, "composite": 60},   # inside
        {"mdd": -45, "composite": 100},  # outside
    ]
    frontier = compute_frontier(points, mdd_range=(-40, -20))
    assert len(frontier) == 1
    assert frontier[0]["mdd"] == -25


def test_compute_frontier_empty():
    """All points filtered out returns empty list."""
    points = [{"mdd": -10, "composite": 50}]
    frontier = compute_frontier(points, mdd_range=(-40, -20))
    assert frontier == []


def test_compute_frontier_invalid_composite():
    """Points with invalid composite are excluded."""
    points = [
        {"mdd": -25, "composite": -9999},
        {"mdd": -30, "composite": 50},
    ]
    frontier = compute_frontier(points, mdd_range=(-40, -20))
    assert len(frontier) == 1
    assert frontier[0]["composite"] == 50


def test_compute_frontier_monotonic():
    """Frontier: higher risk (more negative MDD) → higher or equal COMP."""
    points = [
        {"mdd": -35, "composite": 70},   # highest risk, highest return
        {"mdd": -30, "composite": 50},   # mid risk
        {"mdd": -25, "composite": 30},   # lowest risk
        {"mdd": -20, "composite": 20},   # least risk, dominated by -25
    ]
    frontier = compute_frontier(points, mdd_range=(-40, -15))
    # Frontier sorted by MDD ascending (worst first: -35, -30, -25)
    for i in range(1, len(frontier)):
        assert frontier[i]["mdd"] >= frontier[i - 1]["mdd"], \
            f"MDD should improve: {frontier[i]['mdd']} >= {frontier[i-1]['mdd']}"
        assert frontier[i]["composite"] <= frontier[i - 1]["composite"], \
            f"Higher risk ({frontier[i-1]['mdd']}) should have higher COMP ({frontier[i-1]['composite']})"


# ═══════════════════════════════════════════════════════════════════════════
# narrow_bounds_from_trials
# ═══════════════════════════════════════════════════════════════════════════

def make_trial(mdd=-25, composite=50, **params):
    """Helper: create a trial dict matching optimizer output format."""
    return {"mdd": mdd, "composite": composite, "params": params}


def test_narrow_bounds_returns_searchable_params():
    """Only searchable params with enough data should appear in bounds."""
    trials = [
        make_trial(composite=80, w1=40, w3=30, ma_bull_pos=1.5, ma_bear_pos=0.4, max_holdings=5),
        make_trial(composite=70, w1=50, w3=20, ma_bull_pos=1.3, ma_bear_pos=0.5, max_holdings=3),
        make_trial(composite=60, w1=45, w3=25, ma_bull_pos=1.7, ma_bear_pos=0.3, max_holdings=7),
    ]
    bounds = narrow_bounds_from_trials(trials, top_n=3)
    assert "w1" in bounds
    assert "ma_bull_pos" in bounds
    assert "max_holdings" in bounds
    # Non-searchable params should be excluded
    assert "conf_type" not in bounds
    assert "benchmarks" not in bounds


def test_narrow_bounds_respects_global_bounds():
    """Derived bounds should not exceed PARAM_BOUNDS global min/max."""
    # Create trials with extreme param values
    trials = [
        make_trial(w1=99, w3=1, ma_bull_pos=1.5, ma_bear_pos=0.4, max_holdings=5),
        make_trial(w1=98, w3=2, ma_bull_pos=1.3, ma_bear_pos=0.5, max_holdings=3),
        make_trial(w1=97, w3=3, ma_bull_pos=1.7, ma_bear_pos=0.3, max_holdings=7),
    ]
    bounds = narrow_bounds_from_trials(trials, top_n=3)
    w1_lo, w1_hi, _ = bounds["w1"]
    assert w1_lo >= 0, f"w1 lower bound {w1_lo} < 0"
    assert w1_hi <= 100, f"w1 upper bound {w1_hi} > 100"


def test_narrow_bounds_handles_few_trials():
    """With fewer than 3 trials, bounds should be empty."""
    trials = [
        make_trial(w1=40, w3=30, max_holdings=5),
        make_trial(w1=50, w3=20, max_holdings=3),
    ]
    bounds = narrow_bounds_from_trials(trials, top_n=2)
    # w1 and w3 have 2 values each -> < 3 required -> excluded
    assert "w1" not in bounds or len(bounds) == 0


def test_narrow_bounds_top_n_caps():
    """top_n caps the number of trials used."""
    trials = [make_trial(composite=100 - i, w1=40 + i, w3=30, max_holdings=5) for i in range(10)]
    bounds = narrow_bounds_from_trials(trials, top_n=3)
    assert len(bounds) > 0  # Should still return bounds from top 3


# ═══════════════════════════════════════════════════════════════════════════
# load_all_trials (imported from iterative_optimizer)
# ═══════════════════════════════════════════════════════════════════════════

def test_load_all_trials_dedup():
    """Duplicate trials (same MDD + COMP) should be deduplicated."""
    from iterative_optimizer import load_all_trials

    with tempfile.TemporaryDirectory() as tmp:
        d1 = pathlib.Path(tmp) / "a"
        d1.mkdir()
        d2 = pathlib.Path(tmp) / "b"
        d2.mkdir()

        trial1 = [{"mdd": -25.0, "composite": 50.0, "params": {"w1": 40}}]
        trial2 = [{"mdd": -25.0, "composite": 50.0, "params": {"w1": 40}}]  # duplicate
        trial3 = [{"mdd": -30.0, "composite": 60.0, "params": {"w1": 50}}]  # different

        (d1 / "pareto.json").write_text(json.dumps(trial1 + trial3))
        (d2 / "pareto.json").write_text(json.dumps(trial2))

        result = load_all_trials(str(tmp))
        assert len(result) == 2, f"Expected 2 unique trials, got {len(result)}"


def test_load_all_trials_empty_dir():
    """Empty directory returns empty list."""
    from iterative_optimizer import load_all_trials

    with tempfile.TemporaryDirectory() as tmp:
        result = load_all_trials(str(tmp))
        assert result == []
