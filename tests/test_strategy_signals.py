"""Teknik analiz stratejileri ve sinyal modeli testleri."""

from __future__ import annotations

import math
from collections.abc import Sequence

import pytest

from app.strategies import (
    EMACrossoverStrategy,
    MACDCrossoverStrategy,
    RSIStrategy,
    SMACrossoverStrategy,
    Strategy,
    TrendRSIStrategy,
)
from app.strategies.base import Signal, SignalType


def _scan(strategy: Strategy, closes: Sequence[float]) -> set[SignalType]:
    """Serinin tüm ön eklerinde üretilen sinyal tiplerini toplar."""
    return {strategy.generate("X", closes[: i + 1]).type for i in range(len(closes))}


# --------------------------------------------------------------------------- #
# Signal modeli
# --------------------------------------------------------------------------- #


def test_signal_is_immutable() -> None:
    signal = Signal(symbol="AAPL", type=SignalType.BUY, strength=0.5)
    with pytest.raises(AttributeError):
        signal.strength = 0.9  # type: ignore[misc]


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, -0.1, 1.1])
def test_signal_rejects_invalid_strength(bad: float) -> None:
    with pytest.raises(ValueError):
        Signal(symbol="AAPL", type=SignalType.BUY, strength=bad)


def test_signal_rejects_empty_symbol() -> None:
    with pytest.raises(ValueError):
        Signal(symbol="  ", type=SignalType.HOLD)


def test_signal_carries_metadata() -> None:
    signal = Signal(
        symbol="AAPL",
        type=SignalType.BUY,
        strength=1.0,
        reason="test",
        strategy="sma_crossover",
    )
    assert signal.reason == "test"
    assert signal.strategy == "sma_crossover"


# --------------------------------------------------------------------------- #
# Ortak strateji davranışları (tüm stratejiler için parametrik)
# --------------------------------------------------------------------------- #

_STRATEGIES: list[Strategy] = [
    SMACrossoverStrategy(2, 4),
    EMACrossoverStrategy(2, 4),
    RSIStrategy(2, 30, 70),
    MACDCrossoverStrategy(2, 4, 2),
    TrendRSIStrategy(5, 3, 45, 55),
]


@pytest.mark.parametrize("strategy", _STRATEGIES, ids=lambda s: s.name)
def test_hold_on_insufficient_data(strategy: Strategy) -> None:
    signal = strategy.generate("AAPL", [1.0, 2.0])
    assert signal.type is SignalType.HOLD


@pytest.mark.parametrize("strategy", _STRATEGIES, ids=lambda s: s.name)
def test_hold_on_non_finite_input(strategy: Strategy) -> None:
    closes = [float(i) for i in range(1, 40)]
    closes[10] = math.nan
    signal = strategy.generate("AAPL", closes)
    assert signal.type is SignalType.HOLD
    closes[10] = math.inf
    assert strategy.generate("AAPL", closes).type is SignalType.HOLD


@pytest.mark.parametrize("strategy", _STRATEGIES, ids=lambda s: s.name)
def test_deterministic(strategy: Strategy) -> None:
    closes = [float(i % 7 + 1) for i in range(60)]
    assert strategy.generate("AAPL", closes) == strategy.generate("AAPL", closes)


@pytest.mark.parametrize("strategy", _STRATEGIES, ids=lambda s: s.name)
def test_no_look_ahead_bias(strategy: Strategy) -> None:
    base = [float(i % 5 + 10) for i in range(40)]
    future_a = base + [1_000.0, 2_000.0]
    future_b = base + [1.0, 1.0]
    n = len(base)
    # Aynı ilk n bar, farklı gelecek: sinyal yalnızca ilk n bara bağlı olmalı.
    assert strategy.generate("X", future_a[:n]) == strategy.generate("X", future_b[:n])
    assert strategy.generate("X", future_a[:n]) == strategy.generate("X", base)


# --------------------------------------------------------------------------- #
# Parametre doğrulaması
# --------------------------------------------------------------------------- #


def test_invalid_parameters() -> None:
    with pytest.raises(ValueError):
        SMACrossoverStrategy(5, 5)
    with pytest.raises(ValueError):
        EMACrossoverStrategy(10, 3)
    with pytest.raises(ValueError):
        RSIStrategy(0)
    with pytest.raises(ValueError):
        RSIStrategy(14, oversold=80, overbought=70)
    with pytest.raises(ValueError):
        MACDCrossoverStrategy(26, 12)
    with pytest.raises(ValueError):
        MACDCrossoverStrategy(signal_period=0)
    with pytest.raises(ValueError):
        TrendRSIStrategy(rsi_buy_below=60, rsi_sell_above=40)


# --------------------------------------------------------------------------- #
# BUY / SELL üretimi (her strateji)
# --------------------------------------------------------------------------- #


def test_sma_crossover_buy_and_sell() -> None:
    strat = SMACrossoverStrategy(2, 4)
    assert SignalType.BUY in _scan(strat, [20, 18, 16, 14, 12, 14, 17, 21, 26, 32])
    assert SignalType.SELL in _scan(strat, [12, 14, 17, 21, 26, 32, 30, 25, 20, 16, 13, 10])


def test_ema_crossover_buy_and_sell() -> None:
    strat = EMACrossoverStrategy(2, 4)
    assert SignalType.BUY in _scan(strat, [20, 18, 16, 14, 12, 14, 17, 21, 26, 32])
    assert SignalType.SELL in _scan(strat, [12, 14, 17, 21, 26, 32, 30, 25, 20, 16, 13, 10])


def test_rsi_buy_and_sell() -> None:
    strat = RSIStrategy(2, 30, 70)
    assert strat.generate("X", [100, 90, 80, 70, 60]).type is SignalType.BUY
    assert strat.generate("X", [60, 70, 80, 90, 100]).type is SignalType.SELL


def test_macd_crossover_buy_and_sell() -> None:
    strat = MACDCrossoverStrategy(2, 4, 2)
    assert SignalType.BUY in _scan(strat, [100, 90, 80, 70, 60, 50, 55, 65, 80, 100, 125, 150])
    assert SignalType.SELL in _scan(strat, [10, 13, 17, 22, 28, 35, 33, 29, 24, 18, 13, 9, 6])


def test_trend_rsi_buy_and_sell() -> None:
    strat = TrendRSIStrategy(5, 3, 45, 55)
    buy_series = [30, 28, 26, 24, 22, 20, 18, 16, 14, 12, 10, 11, 12, 13]
    sell_series = [10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 29, 28, 27]
    assert SignalType.BUY in _scan(strat, buy_series)
    assert SignalType.SELL in _scan(strat, sell_series)


def test_signal_strength_within_unit_interval() -> None:
    strat = RSIStrategy(2, 30, 70)
    signal = strat.generate("X", [100, 90, 80, 70, 60])
    assert 0.0 <= signal.strength <= 1.0
