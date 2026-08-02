"""Paper trading orchestrator sonuç modelleri."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.brokers.base import OrderSide
from app.strategies.base import Signal


@dataclass(frozen=True)
class GeneratedSignal:
    """Bir barda üretilen birleşik sinyal."""

    timestamp: datetime
    signal: Signal


@dataclass(frozen=True)
class AcceptedOrder:
    """Kabul edilip gerçekleşen paper emir."""

    timestamp: datetime
    side: OrderSide
    quantity: float
    price: float

    @property
    def notional(self) -> float:
        """İşlem tutarı (adet * fiyat)."""
        return self.quantity * self.price


@dataclass(frozen=True)
class RejectedOrder:
    """Reddedilen emir ve red nedeni."""

    timestamp: datetime
    side: OrderSide
    requested_quantity: float
    reason: str


@dataclass(frozen=True)
class EquityPoint:
    """Özkaynak eğrisindeki tek bir nokta."""

    timestamp: datetime
    equity: float


@dataclass(frozen=True)
class PaperTradingResult:
    """Bir paper trading çalışmasının tam sonucu."""

    symbol: str
    initial_cash: float
    ending_cash: float
    final_equity: float
    positions: tuple[tuple[str, float], ...]
    signals: tuple[GeneratedSignal, ...]
    accepted_orders: tuple[AcceptedOrder, ...]
    rejected_orders: tuple[RejectedOrder, ...]
    equity_curve: tuple[EquityPoint, ...]

    @property
    def num_accepted(self) -> int:
        """Kabul edilen emir sayısı."""
        return len(self.accepted_orders)

    @property
    def num_rejected(self) -> int:
        """Reddedilen emir sayısı."""
        return len(self.rejected_orders)

    @property
    def total_return(self) -> float:
        """Toplam getiri oranı ((son equity - ilk nakit) / ilk nakit)."""
        if self.initial_cash <= 0:
            return 0.0
        return (self.final_equity - self.initial_cash) / self.initial_cash
