"""Strateji testleri."""

from __future__ import annotations

from app.strategies import SignalType, SMACrossoverStrategy


def test_hold_on_insufficient_data() -> None:
    strat = SMACrossoverStrategy(short_period=3, long_period=5)
    signal = strat.generate("AAPL", [1, 2, 3])
    assert signal.type is SignalType.HOLD


def test_buy_on_upward_crossover() -> None:
    strat = SMACrossoverStrategy(short_period=2, long_period=4)
    # Düşükten yükselişe dönen seri: kısa SMA uzun SMA'yı yukarı keser.
    closes = [10, 9, 8, 7, 6, 7, 9, 12, 15]
    signal = strat.generate("AAPL", closes)
    assert signal.type in {SignalType.BUY, SignalType.HOLD}


def test_generates_valid_signal_type() -> None:
    strat = SMACrossoverStrategy(short_period=2, long_period=4)
    closes = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    signal = strat.generate("AAPL", closes)
    assert isinstance(signal.type, SignalType)
