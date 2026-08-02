"""Paper trading orchestrator testleri."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

import pytest

from app.brokers.base import OrderSide
from app.core.kill_switch import kill_switch
from app.market_data import BarSeries, Timeframe
from app.market_data.base import Bar
from app.paper_trading import OrchestratorConfig, PaperTradingOrchestrator
from app.risk.limits import RiskManager
from app.signals import SignalEngine
from app.strategies.base import Signal, SignalType, Strategy


class ScheduledStrategy(Strategy):
    """Bar indeksine göre önceden belirlenmiş sinyaller üreten test stratejisi."""

    name = "scheduled"

    def __init__(self, signals: dict[int, SignalType]) -> None:
        self._signals = signals

    def generate(self, symbol: str, closes: Sequence[float]) -> Signal:
        signal_type = self._signals.get(len(closes) - 1, SignalType.HOLD)
        return Signal(symbol=symbol, type=signal_type, strength=1.0, strategy=self.name)


class OversizingRiskManager(RiskManager):
    """Aşırı büyük pozisyon döndürerek yetersiz nakit yolunu tetikler."""

    def position_size(self, *, equity: float, entry_price: float, stop_price: float) -> float:
        return 1_000_000.0


def _engine(signals: dict[int, SignalType]) -> SignalEngine:
    return SignalEngine([ScheduledStrategy(signals)])


def _series(open_close: Sequence[tuple[float, float]], symbol: str = "AAPL") -> BarSeries:
    bars = [
        Bar(
            symbol=symbol,
            timestamp=datetime(2024, 1, 1) + timedelta(days=i),
            open=o,
            high=max(o, c) + 1.0,
            low=min(o, c) - 1.0,
            close=c,
            volume=1000,
        )
        for i, (o, c) in enumerate(open_close)
    ]
    return BarSeries.from_bars(symbol, Timeframe.D1, bars)


def test_result_shapes() -> None:
    series = _series([(10, 10), (10, 11), (12, 12)])
    result = PaperTradingOrchestrator(_engine({})).run(series)
    assert len(result.signals) == len(series)
    assert len(result.equity_curve) == len(series)
    assert result.initial_cash == 100_000.0
    assert result.num_accepted == 0


def test_signal_on_bar_fills_on_next_bar_open() -> None:
    series = _series([(10, 10), (10, 11), (50, 55)])
    result = PaperTradingOrchestrator(_engine({1: SignalType.BUY})).run(series)
    assert result.num_accepted == 1
    order = result.accepted_orders[0]
    assert order.side is OrderSide.BUY
    assert order.timestamp == series[2].timestamp
    assert order.price == pytest.approx(50.0)


def test_last_bar_signal_is_not_filled() -> None:
    series = _series([(10, 10), (10, 11), (50, 55)])
    result = PaperTradingOrchestrator(_engine({2: SignalType.BUY})).run(series)
    assert result.num_accepted == 0


def test_short_selling_is_rejected() -> None:
    series = _series([(100, 100), (100, 101)])
    result = PaperTradingOrchestrator(_engine({0: SignalType.SELL})).run(series)
    assert result.num_accepted == 0
    assert result.num_rejected == 1
    assert "Short selling" in result.rejected_orders[0].reason


def test_insufficient_cash_is_rejected() -> None:
    series = _series([(100, 100), (100, 101)])
    orch = PaperTradingOrchestrator(
        _engine({0: SignalType.BUY}), risk_manager=OversizingRiskManager()
    )
    result = orch.run(series)
    assert result.num_accepted == 0
    assert result.num_rejected == 1
    assert "Yetersiz nakit" in result.rejected_orders[0].reason
    assert result.ending_cash == result.initial_cash


def test_sell_only_disposes_held_quantity() -> None:
    series = _series([(100, 100), (100, 110), (120, 120), (130, 130)])
    result = PaperTradingOrchestrator(_engine({0: SignalType.BUY, 1: SignalType.SELL})).run(series)
    sides = [o.side for o in result.accepted_orders]
    assert sides == [OrderSide.BUY, OrderSide.SELL]
    assert result.accepted_orders[1].quantity == pytest.approx(result.accepted_orders[0].quantity)
    assert result.positions == ()


def test_commission_applied_to_fill_price() -> None:
    series = _series([(100, 100), (100, 101)])
    orch = PaperTradingOrchestrator(
        _engine({0: SignalType.BUY}), OrchestratorConfig(commission_rate=0.01)
    )
    result = orch.run(series)
    assert result.accepted_orders[0].price == pytest.approx(101.0)


def test_slippage_applied_to_buy_and_sell() -> None:
    series = _series([(100, 100), (100, 110), (100, 90)])
    orch = PaperTradingOrchestrator(
        _engine({0: SignalType.BUY, 1: SignalType.SELL}),
        OrchestratorConfig(slippage_rate=0.02),
    )
    result = orch.run(series)
    assert result.accepted_orders[0].price == pytest.approx(102.0)
    assert result.accepted_orders[1].price == pytest.approx(98.0)


def test_kill_switch_blocks_all_orders() -> None:
    kill_switch.engage("test")
    try:
        series = _series([(100, 100), (100, 101), (102, 103)])
        result = PaperTradingOrchestrator(_engine({0: SignalType.BUY})).run(series)
        assert result.num_accepted == 0
        assert all(gs.signal.type is SignalType.HOLD for gs in result.signals)
    finally:
        kill_switch.reset()


def test_orchestrator_is_deterministic() -> None:
    series = _series([(100, 100), (100, 110), (120, 120), (130, 130)])
    orch = PaperTradingOrchestrator(
        _engine({0: SignalType.BUY, 1: SignalType.SELL}),
        OrchestratorConfig(commission_rate=0.001, slippage_rate=0.002),
    )
    assert orch.run(series) == orch.run(series)


def test_config_validation() -> None:
    with pytest.raises(ValueError):
        OrchestratorConfig(initial_cash=0)
    with pytest.raises(ValueError):
        OrchestratorConfig(commission_rate=-0.01)
    with pytest.raises(ValueError):
        OrchestratorConfig(commission_rate=1.0)
    with pytest.raises(ValueError):
        OrchestratorConfig(slippage_rate=1.5)
    with pytest.raises(ValueError):
        OrchestratorConfig(stop_loss_pct=0)
    for bad in (float("nan"), float("inf")):
        with pytest.raises(ValueError):
            OrchestratorConfig(initial_cash=bad)
        with pytest.raises(ValueError):
            OrchestratorConfig(commission_rate=bad)
