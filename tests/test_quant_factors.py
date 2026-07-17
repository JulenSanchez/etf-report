"""
REQ-200: F7 对数收益偏离因子 — 单元测试
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from quant_factors import factor_log_return_deviation, map_f7, composite_score


def make_rw(n=300, seed=42, start_price=10.0):
    """Synthetic random-walk daily data."""
    rng = np.random.default_rng(seed)
    log_ret = rng.normal(0, 0.02, n - 1)
    close = start_price * np.cumprod(np.exp(log_ret))
    close = np.insert(close, 0, start_price)
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    return pd.DataFrame({"date": dates, "close": close})


# ── factor_log_return_deviation ──────────────────────────

def test_log_return_additivity():
    """对数收益率可加性：2 日 ln(P2/P0) == r1 + r2"""
    df = make_rw(n=100)
    c = df["close"].values
    r1 = np.log(c[1] / c[0])
    r2 = np.log(c[2] / c[1])
    direct = np.log(c[2] / c[0])
    assert abs((r1 + r2) - direct) < 1e-12


def test_f7_short_history_returns_nan():
    """数据不足 60 天 → NaN"""
    df = make_rw(n=50)
    z = factor_log_return_deviation(df, window=20, lookback=250, min_days=60)
    assert np.isnan(z)


def test_f7_returns_value_with_sufficient_data():
    """300 天随机游走 → 应返回有限 Z"""
    df = make_rw(n=300)
    z = factor_log_return_deviation(df, window=20, lookback=250, min_days=60)
    assert not np.isnan(z)
    assert -5 < z < 5


def test_f7_near_zero_for_flat_prices():
    """价格几乎不变 → 累计对数收益≈0 → Z≈0"""
    n = 300
    close = np.full(n, 100.0)
    close[0] = 99.9  # tiny variation
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    df = pd.DataFrame({"date": dates, "close": close})
    z = factor_log_return_deviation(df, window=20, lookback=250, min_days=60, sigma_floor=0.005)
    assert abs(z) < 2.0


def test_f7_extreme_trend():
    """最后 20 天加速暴涨 → Z 应为正（高估）"""
    n = 300
    rng = np.random.default_rng(42)
    # 前 280 天：平稳随机游走
    log_ret = rng.normal(0, 0.015, n - 1)
    # 最后 20 天：加速暴涨（日涨 3%）
    log_ret[-20:] = 0.03
    close = 10.0 * np.cumprod(np.exp(np.insert(log_ret, 0, 0)))
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    df = pd.DataFrame({"date": dates, "close": close})
    z = factor_log_return_deviation(df, window=20, lookback=250, min_days=60)
    assert z > 1.5  # significantly positive — 20d cumulative far above history


def test_f7_extreme_crash():
    """最后 20 天加速暴跌 → Z 应为负（低估）"""
    n = 300
    rng = np.random.default_rng(42)
    # 前 280 天：平稳随机游走
    log_ret = rng.normal(0, 0.015, n - 1)
    # 最后 20 天：加速暴跌（日跌 3%）
    log_ret[-20:] = -0.03
    close = 10.0 * np.cumprod(np.exp(np.insert(log_ret, 0, 0)))
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    df = pd.DataFrame({"date": dates, "close": close})
    z = factor_log_return_deviation(df, window=20, lookback=250, min_days=60)
    assert z < -1.5  # significantly negative — 20d cumulative far below history


def test_f7_none_input():
    assert np.isnan(factor_log_return_deviation(None))


# ── map_f7 ───────────────────────────────────────────────

def test_map_f7_neutral():
    """Z=0 → 0.5"""
    assert map_f7(0.0) == pytest.approx(0.5, abs=1e-6)


def test_map_f7_overbought():
    """Z=+2 → 低于中性分（高估减分）"""
    assert map_f7(2.0) == pytest.approx(0.4707, abs=0.001)


def test_map_f7_oversold():
    """Z=-2 → 高于中性分（超跌加分）"""
    assert map_f7(-2.0) == pytest.approx(0.5293, abs=0.001)


def test_map_f7_nan():
    assert np.isnan(map_f7(np.nan))


def test_map_f7_monotonic():
    """映射函数单调递减：Z 越大分数越低"""
    for z in [-3, -2, -1, 0, 1, 2]:
        assert map_f7(z) > map_f7(z + 1)


def test_map_f7_sensitivity():
    """k 更大时，同样 Z 值的响应更平缓"""
    assert map_f7(2.0, up_span=5.0) > map_f7(2.0, up_span=3.0)
    assert map_f7(-2.0, up_span=5.0) < map_f7(-2.0, up_span=3.0)


def test_map_f7_asymmetric_sides():
    """REQ-375: 超跌侧独立参数生效——down 参数只影响 Z<0，不影响 Z>0"""
    base_up = map_f7(2.0, up_power=7.0, up_span=3.0)
    base_down = map_f7(-2.0, up_power=7.0, up_span=3.0)
    # 改 down 参数：超涨侧分数不变，超跌侧分数变化
    assert map_f7(2.0, up_power=7.0, up_span=3.0, down_power=14.0, down_span=2.5) == pytest.approx(base_up, abs=1e-9)
    assert map_f7(-2.0, up_power=7.0, up_span=3.0, down_power=14.0, down_span=2.5) != pytest.approx(base_down, abs=1e-6)


def test_composite_score_consumes_f7_down_params():
    """composite_score 内部评分路径消费 f7_down_power/f7_down_span（超跌侧接入）"""
    factors_df = pd.DataFrame({
        "f1_ema_dev": [0.0, 0.0],
        "f3_volume_ratio": [1.0, 1.0],
        "f7_log_return_dev": [2.0, -2.0],  # 一个超涨、一个超跌
    }, index=["UP_ETF", "DOWN_ETF"])
    weights = {"ema_deviation": 0.0, "volume_ratio": 0.0, "log_return_deviation": 1.0}
    base = composite_score(factors_df, weights,
                           sensitivity={"f7_up_power": 7.0, "f7_up_span": 3.0,
                                        "f7_down_power": 7.0, "f7_down_span": 3.0})
    tuned = composite_score(factors_df, weights,
                            sensitivity={"f7_up_power": 7.0, "f7_up_span": 3.0,
                                         "f7_down_power": 14.0, "f7_down_span": 2.5})
    # 超涨 ETF 不受 down 参数影响；超跌 ETF 分数随 down 参数变化
    assert tuned["UP_ETF"] == pytest.approx(base["UP_ETF"], abs=1e-9)
    assert tuned["DOWN_ETF"] != pytest.approx(base["DOWN_ETF"], abs=1e-6)


# ── F6 (factor_exhaustion_penalty): removed in REQ-255 ──
# Function was retired along with momentum exhaustion logic.
# Tests removed. See Archive.md REQ-255 for rationale.
