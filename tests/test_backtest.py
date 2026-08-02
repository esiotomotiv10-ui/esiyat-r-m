"""Backtest motoru testleri."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

import pytest

from app.backtest import BacktestConfig, BacktestEngine
from app.brokers.base import OrderSide
from app.core.kill_switch import kill_switch
from app.market_data import BarSeries, Timeframe
from app.market_data.base import Bar
from app.risk.limits import RiskManager
from app.strategies import SMACrossoverStrategy
from app.strategies.base import Signal, SignalType, Strategy


class ScheduledStrategy(Strategy):
    name = "scheduled"

    def __init__(self, signals: dict[int, SignalType]) -> None:
        self._signals = signals

    def generate(self, symbol: str, closes: Sequence[float]) -> Signal:
        signal_type = self._signals.get(len(closes) - 1, SignalType.HOLD)
        return Signal(symbol=symbol, type=signal_type, strength=1.0)


class OversizingRiskManager(RiskManager):
    def position_size(
        self,
        *,
        equity: float,
        entry_price: float,
        stop_price: float,
    ) -> float:
        return 1_000_000.0


def _series_from_closes(closes: Sequence[float], symbol: str = "AAPL") -> BarSeries:
    bars = [
        Bar(
            symbol=symbol,
            timestamp=datetime(2024, 1, 1) + timedelta(days=i),
            open=c,
            high=c + 0.5,
            low=c - 0.5,
            close=c,
            volume=1000,
        )
        for i, c in enumerate(closes)
    ]
    return BarSeries.from_bars(symbol, Timeframe.D1, bars)


def _series_from_ohlc(open_close: Sequence[tuple[float, float]], symbol: str = "AAPL") -> BarSeries:
    bars = [
        Bar(
            symbol=symbol,
            timestamp=datetime(2024, 1, 1) + timedelta(days=i),
            open=open_price,
            high=max(open_price, close_price) + 1.0,
            low=min(open_price, close_price) - 1.0,
            close=close_price,
            volume=1000,
        )
        for i, (open_price, close_price) in enumerate(open_close)
    ]
    return BarSeries.from_bars(symbol, Timeframe.D1, bars)


def test_config_validation() -> None:
    with pytest.raises(ValueError):
        BacktestConfig(initial_cash=0)
    with pytest.raises(ValueError):
        BacktestConfig(stop_loss_pct=0)
    with pytest.raises(ValueError):
        BacktestConfig(stop_loss_pct=1)
    with pytest.raises(ValueError):
        BacktestConfig(warmup=-1)
    for value in (float("nan"), float("inf")):
        with pytest.raises(ValueError):
            BacktestConfig(initial_cash=value)
        with pytest.raises(ValueError):
            BacktestConfig(stop_loss_pct=value)
        with pytest.raises(ValueError):
            BacktestConfig(commission_rate=value)
        with pytest.raises(ValueError):
            BacktestConfig(slippage_rate=value)
    with pytest.raises(ValueError):
        BacktestConfig(commission_rate=-0.01)
    with pytest.raises(ValueError):
        BacktestConfig(slippage_rate=-0.01)


def test_backtest_tracks_equity_curve() -> None:
    closes = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
    series = _series_from_closes(closes)
    engine = BacktestEngine(SMACrossoverStrategy(short_period=2, long_period=4))
    result = engine.run(series)
    assert len(result.equity_curve) == len(series)
    assert result.initial_equity == 100_000.0
    assert result.final_equity > 0
    assert 0.0 <= result.max_drawdown <= 1.0
    assert isinstance(result.total_return, float)


def test_backtest_generates_buy_trade_on_golden_cross() -> None:
    # V-şekilli seri: düşüşten yükselişe dönüşte golden cross oluşur.
    closes = [20, 18, 16, 14, 12, 14, 17, 21, 26, 32]
    series = _series_from_closes(closes)
    engine = BacktestEngine(SMACrossoverStrategy(short_period=2, long_period=4))
    result = engine.run(series)
    assert result.num_trades >= 1
    assert result.trades[0].side is OrderSide.BUY
    # Tüm işlemler paper (yerleşik broker) üzerinden gerçekleşmiştir.
    assert all(t.quantity > 0 for t in result.trades)


def test_signal_on_bar_t_fills_on_next_bar_open() -> None:
    series = _series_from_ohlc([(10, 10), (10, 11), (50, 55)])
    engine = BacktestEngine(ScheduledStrategy({1: SignalType.BUY}))
    result = engine.run(series)
    assert result.num_trades == 1
    assert result.trades[0].timestamp == series[2].timestamp
    assert result.trades[0].price == 50


def test_last_bar_signal_is_not_filled() -> None:
    series = _series_from_ohlc([(10, 10), (10, 11), (50, 55)])
    engine = BacktestEngine(ScheduledStrategy({2: SignalType.BUY}))
    result = engine.run(series)
    assert result.num_trades == 0


def test_backtest_respects_real_kill_switch() -> None:
    kill_switch.engage("test")
    try:
        series = _series_from_ohlc([(10, 10), (10, 11), (50, 55)])
        engine = BacktestEngine(ScheduledStrategy({1: SignalType.BUY}))
        result = engine.run(series)
        assert result.num_trades == 0
    finally:
        kill_switch.reset()


def test_commission_applied_to_buy_fill_price() -> None:
    series = _series_from_ohlc([(100, 100), (100, 101)])
    engine = BacktestEngine(
        ScheduledStrategy({0: SignalType.BUY}),
        BacktestConfig(commission_rate=0.01),
    )
    result = engine.run(series)
    assert result.trades[0].price == pytest.approx(101.0)


def test_slippage_applied_to_buy_and_sell_fill_prices() -> None:
    series = _series_from_ohlc([(100, 100), (100, 110), (100, 90)])
    engine = BacktestEngine(
        ScheduledStrategy({0: SignalType.BUY, 1: SignalType.SELL}),
        BacktestConfig(slippage_rate=0.02),
    )
    result = engine.run(series)
    assert [trade.side for trade in result.trades] == [OrderSide.BUY, OrderSide.SELL]
    assert result.trades[0].price == pytest.approx(102.0)
    assert result.trades[1].price == pytest.approx(98.0)


def test_backtest_rejects_insufficient_cash_safely() -> None:
    series = _series_from_ohlc([(100, 100), (100, 101)])
    engine = BacktestEngine(
        ScheduledStrategy({0: SignalType.BUY}),
        risk_manager=OversizingRiskManager(),
    )
    result = engine.run(series)
    assert result.num_trades == 0
    assert result.ending_cash == result.initial_cash


def test_short_selling_is_rejected() -> None:
    series = _series_from_ohlc([(100, 100), (100, 101)])
    engine = BacktestEngine(ScheduledStrategy({0: SignalType.SELL}))
    result = engine.run(series)
    assert result.num_trades == 0


def test_oversell_signal_sells_only_held_position() -> None:
    series = _series_from_ohlc([(100, 100), (100, 110), (120, 120), (130, 130)])
    engine = BacktestEngine(ScheduledStrategy({0: SignalType.BUY, 1: SignalType.SELL}))
    result = engine.run(series)
    assert [trade.side for trade in result.trades] == [OrderSide.BUY, OrderSide.SELL]
    assert result.trades[1].quantity == pytest.approx(result.trades[0].quantity)


def test_real_win_loss_matching_uses_buy_sell_pairs() -> None:
    series = _series_from_ohlc([(100, 100), (100, 110), (120, 120), (130, 130)])
    engine = BacktestEngine(ScheduledStrategy({0: SignalType.BUY, 1: SignalType.SELL}))
    result = engine.run(series)
    assert result.winning_trades == 1
    assert result.losing_trades == 0
    assert result.win_rate == 1.0
    assert result.trades[1].realized_pnl > 0


def test_backtest_is_deterministic() -> None:
    series = _series_from_ohlc([(100, 100), (100, 110), (120, 120), (130, 130)])
    engine = BacktestEngine(
        ScheduledStrategy({0: SignalType.BUY, 1: SignalType.SELL}),
        BacktestConfig(commission_rate=0.001, slippage_rate=0.002),
    )
    first = engine.run(series)
    second = engine.run(series)
    assert first == second


def test_backtest_respects_asset_weight_limit() -> None:
    closes = [20, 18, 16, 14, 12, 14, 17, 21, 26, 32]
    series = _series_from_closes(closes)
    engine = BacktestEngine(SMACrossoverStrategy(short_period=2, long_period=4))
    result = engine.run(series)
    buys = [t for t in result.trades if t.side is OrderSide.BUY]
    assert buys
    # Tek varlık ağırlığı %10 limitini aşmamalı (giriş tutarı).
    assert buys[0].notional <= 0.10 * result.initial_equity + 1e-6


def test_backtest_buy_then_sell_cycle() -> None:
    # Önce yükseliş (alış), sonra düşüş (satış) döngüsü.
    closes = [12, 14, 17, 21, 26, 32, 30, 25, 20, 16, 13]
    series = _series_from_closes(closes)
    engine = BacktestEngine(SMACrossoverStrategy(short_period=2, long_period=4))
    result = engine.run(series)
    sides = [t.side for t in result.trades]
    if len(sides) >= 2:
        # İlk işlem alış olmalı ve alış/satış sırayla gelmeli.
        assert sides[0] is OrderSide.BUY
        assert sides[1] is OrderSide.SELL


def test_backtest_no_trades_when_flat() -> None:
    closes = [50.0] * 12  # yatay seri → kesişim yok
    series = _series_from_closes(closes)
    engine = BacktestEngine(SMACrossoverStrategy(short_period=2, long_period=4))
    result = engine.run(series)
    assert result.num_trades == 0
    assert result.final_equity == result.initial_equity
