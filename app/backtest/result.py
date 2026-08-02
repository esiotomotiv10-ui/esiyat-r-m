"""Backtest sonuç modelleri ve metrik hesaplamaları."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.brokers.base import OrderSide


@dataclass(frozen=True)
class Trade:
    """Backtest sırasında gerçekleşen tek bir paper işlem."""

    timestamp: datetime
    symbol: str
    side: OrderSide
    quantity: float
    price: float

    @property
    def notional(self) -> float:
        """İşlem tutarı (adet * fiyat)."""
        return self.quantity * self.price


@dataclass(frozen=True)
class EquityPoint:
    """Özkaynak eğrisindeki tek bir nokta."""

    timestamp: datetime
    equity: float


@dataclass(frozen=True)
class BacktestResult:
    """Bir backtest çalışmasının sonucu ve özet metrikleri."""

    symbol: str
    initial_equity: float
    final_equity: float
    equity_curve: tuple[EquityPoint, ...]
    trades: tuple[Trade, ...]

    @property
    def total_return(self) -> float:
        """Toplam getiri oranı ((son - ilk) / ilk)."""
        if self.initial_equity <= 0:
            return 0.0
        return (self.final_equity - self.initial_equity) / self.initial_equity

    @property
    def num_trades(self) -> int:
        """Gerçekleşen işlem sayısı."""
        return len(self.trades)

    @property
    def max_drawdown(self) -> float:
        """Özkaynak eğrisinden hesaplanan azami düşüş oranı (0-1)."""
        peak = self.initial_equity
        max_dd = 0.0
        for point in self.equity_curve:
            peak = max(peak, point.equity)
            if peak > 0:
                dd = (peak - point.equity) / peak
                max_dd = max(max_dd, dd)
        return max_dd
