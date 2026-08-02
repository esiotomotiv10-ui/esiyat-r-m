"""SignalEngine (ağırlıklı sinyal birleştirme) testleri."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from app.core.kill_switch import KillSwitch
from app.signals import SignalEngine
from app.strategies.base import Signal, SignalType, Strategy


class FixedStrategy(Strategy):
    """Girdiden bağımsız olarak sabit bir sinyal döndüren test stratejisi."""

    def __init__(self, name: str, signal_type: SignalType, strength: float) -> None:
        self.name = name
        self._type = signal_type
        self._strength = strength

    def generate(self, symbol: str, closes: Sequence[float]) -> Signal:
        return Signal(symbol=symbol, type=self._type, strength=self._strength, strategy=self.name)


def _closes() -> list[float]:
    return [float(i) for i in range(1, 30)]


def test_single_strategy_passthrough_direction() -> None:
    engine = SignalEngine([FixedStrategy("a", SignalType.BUY, 1.0)])
    result = engine.evaluate("AAPL", _closes())
    assert result.signal.type is SignalType.BUY
    assert result.net_score == pytest.approx(1.0)


def test_agreeing_strategies_combine() -> None:
    engine = SignalEngine(
        [FixedStrategy("a", SignalType.BUY, 1.0), FixedStrategy("b", SignalType.BUY, 0.5)],
    )
    result = engine.evaluate("AAPL", _closes())
    assert result.signal.type is SignalType.BUY
    assert result.net_score == pytest.approx(0.75)  # (1.0 + 0.5) / 2


def test_weighted_combination() -> None:
    engine = SignalEngine(
        [FixedStrategy("a", SignalType.BUY, 1.0), FixedStrategy("b", SignalType.SELL, 1.0)],
        weights=[3.0, 1.0],
    )
    result = engine.evaluate("AAPL", _closes())
    assert result.signal.type is SignalType.BUY
    assert result.net_score == pytest.approx(0.5)  # (3*1 - 1*1) / 4


def test_conflicting_signals_return_hold() -> None:
    engine = SignalEngine(
        [FixedStrategy("a", SignalType.BUY, 1.0), FixedStrategy("b", SignalType.SELL, 1.0)],
    )
    result = engine.evaluate("AAPL", _closes())
    assert result.signal.type is SignalType.HOLD
    assert result.net_score == 0.0


def test_min_strength_threshold_returns_hold() -> None:
    engine = SignalEngine(
        [FixedStrategy("a", SignalType.BUY, 1.0), FixedStrategy("b", SignalType.SELL, 1.0)],
        weights=[3.0, 1.0],
        min_strength=0.6,  # net 0.5 < 0.6
    )
    result = engine.evaluate("AAPL", _closes())
    assert result.signal.type is SignalType.HOLD


def test_kill_switch_forces_hold() -> None:
    switch = KillSwitch(initial=True)
    engine = SignalEngine([FixedStrategy("a", SignalType.BUY, 1.0)], switch=switch)
    result = engine.evaluate("AAPL", _closes())
    assert result.signal.type is SignalType.HOLD
    assert "Kill switch" in result.signal.reason
    assert result.components == ()


def test_components_are_recorded() -> None:
    engine = SignalEngine(
        [FixedStrategy("a", SignalType.BUY, 1.0), FixedStrategy("b", SignalType.HOLD, 0.0)],
    )
    result = engine.evaluate("AAPL", _closes())
    assert len(result.components) == 2
    assert {c.strategy for c in result.components} == {"a", "b"}


def test_engine_has_no_order_methods() -> None:
    # SignalEngine yalnızca sinyal üretir; emir gönderme arayüzü olmamalı.
    engine = SignalEngine([FixedStrategy("a", SignalType.HOLD, 0.0)])
    assert not hasattr(engine, "execute")
    assert not hasattr(engine, "submit_order")


def test_min_bars_is_max_of_components() -> None:
    from app.strategies import SMACrossoverStrategy

    engine = SignalEngine([SMACrossoverStrategy(2, 4), SMACrossoverStrategy(5, 20)])
    assert engine.min_bars == 21  # long_period(20) + 1


# --- Parametre doğrulaması ---


def test_requires_at_least_one_strategy() -> None:
    with pytest.raises(ValueError):
        SignalEngine([])


def test_weights_length_must_match() -> None:
    with pytest.raises(ValueError):
        SignalEngine([FixedStrategy("a", SignalType.BUY, 1.0)], weights=[1.0, 2.0])


@pytest.mark.parametrize("bad_weights", [[0.0], [-1.0], [float("nan")], [float("inf")]])
def test_weights_must_be_positive_finite(bad_weights: list[float]) -> None:
    with pytest.raises(ValueError):
        SignalEngine([FixedStrategy("a", SignalType.BUY, 1.0)], weights=bad_weights)


@pytest.mark.parametrize("bad", [-0.1, 1.1])
def test_min_strength_range(bad: float) -> None:
    with pytest.raises(ValueError):
        SignalEngine([FixedStrategy("a", SignalType.BUY, 1.0)], min_strength=bad)
