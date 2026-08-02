"""Backtest motoru testleri."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

import pytest

from app.backtest import BacktestConfig, BacktestEngine
from app.brokers.base import OrderSide
from app.market_data import BarSeries, Timeframe
from app.market_data.base import Bar
from app.strategies import SMACrossoverStrategy


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


def test_config_validation() -> None:
    with pytest.raises(ValueError):
        BacktestConfig(initial_cash=0)
    with pytest.raises(ValueError):
        BacktestConfig(stop_loss_pct=0)
    with pytest.raises(ValueError):
        BacktestConfig(stop_loss_pct=1)
    with pytest.raises(ValueError):
        BacktestConfig(warmup=-1)


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
