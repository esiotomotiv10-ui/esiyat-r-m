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
    realized_pnl: float = 0.0

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
    initial_cash: float
    ending_cash: float
    final_equity: float
    equity_curve: tuple[EquityPoint, ...]
    trades: tuple[Trade, ...]

    @property
    def initial_equity(self) -> float:
        """Geriye dönük uyumluluk için başlangıç özkaynağı."""
        return self.initial_cash

    @property
    def total_return(self) -> float:
        """Toplam getiri oranı ((son - ilk) / ilk)."""
        if self.initial_cash <= 0:
            return 0.0
        return (self.final_equity - self.initial_cash) / self.initial_cash

    @property
    def num_trades(self) -> int:
        """Gerçekleşen işlem sayısı."""
        return len(self.trades)

    @property
    def winning_trades(self) -> int:
        """Gerçekleşmiş eşleşmeye göre kârla kapanan satış sayısı."""
        return sum(
            1 for trade in self.trades if trade.side is OrderSide.SELL and trade.realized_pnl > 0
        )

    @property
    def losing_trades(self) -> int:
        """Gerçekleşmiş eşleşmeye göre zararla kapanan satış sayısı."""
        return sum(
            1 for trade in self.trades if trade.side is OrderSide.SELL and trade.realized_pnl < 0
        )

    @property
    def win_rate(self) -> float:
        """Kapanan işlemler içinde kazanan oranı."""
        closed = self.winning_trades + self.losing_trades
        if closed == 0:
            return 0.0
        return self.winning_trades / closed

    @property
    def max_drawdown(self) -> float:
        """Özkaynak eğrisinden hesaplanan azami düşüş oranı (0-1)."""
        peak = self.initial_cash
        max_dd = 0.0
        for point in self.equity_curve:
            peak = max(peak, point.equity)
            if peak > 0:
                dd = (peak - point.equity) / peak
                max_dd = max(max_dd, dd)
        return max_dd
