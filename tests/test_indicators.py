"""Teknik gösterge testleri."""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.indicators import atr, ema, macd, rsi, sma


def test_sma_basic() -> None:
    result = sma([1, 2, 3, 4, 5], period=3)
    assert math.isnan(result[0])
    assert math.isnan(result[1])
    assert result[2] == 2.0
    assert result[3] == 3.0
    assert result[4] == 4.0


def test_sma_insufficient_data() -> None:
    result = sma([1, 2], period=5)
    assert np.all(np.isnan(result))


def test_ema_seed_and_length() -> None:
    values = [1, 2, 3, 4, 5, 6, 7, 8]
    result = ema(values, period=3)
    assert result.shape[0] == len(values)
    assert math.isnan(result[1])
    # İlk EMA değeri, ilk 3 gözlemin ortalaması (2.0).
    assert result[2] == 2.0
    assert result[-1] > result[2]


def test_rsi_all_gains_is_100() -> None:
    values = list(range(1, 20))  # sürekli artan
    result = rsi(values, period=14)
    assert result[14] == 100.0


def test_rsi_flat_series_is_neutral() -> None:
    result = rsi([100.0] * 20, period=14)
    assert result[14] == 50.0


def test_rsi_range() -> None:
    rng = np.random.default_rng(42)
    values = np.cumsum(rng.normal(size=100)) + 100
    result = rsi(values, period=14)
    valid = result[~np.isnan(result)]
    assert np.all(valid >= 0)
    assert np.all(valid <= 100)


def test_macd_shapes_and_relationship() -> None:
    rng = np.random.default_rng(1)
    values = np.cumsum(rng.normal(size=200)) + 100
    res = macd(values)
    assert res.macd.shape == values.shape
    assert res.signal.shape == values.shape
    assert res.histogram.shape == values.shape
    # Geçerli konumlarda histogram = macd - signal.
    valid = ~np.isnan(res.histogram)
    assert np.allclose(res.histogram[valid], res.macd[valid] - res.signal[valid], equal_nan=False)


def test_atr_positive() -> None:
    high = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25]
    low = [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24]
    close = [
        9.5,
        10.5,
        11.5,
        12.5,
        13.5,
        14.5,
        15.5,
        16.5,
        17.5,
        18.5,
        19.5,
        20.5,
        21.5,
        22.5,
        23.5,
        24.5,
    ]
    result = atr(high, low, close, period=14)
    valid = result[~np.isnan(result)]
    assert np.all(valid > 0)


def test_indicators_reject_non_finite_input() -> None:
    with pytest.raises(ValueError):
        sma([1.0, math.nan, 3.0], period=2)
