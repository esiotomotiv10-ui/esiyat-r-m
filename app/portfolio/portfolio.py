"""Basit paper-trading portföy modeli.

Nakit, pozisyonlar ve gerçekleşmiş kâr/zarar takibi yapar. Tüm işlemler
yalnızca bellekte tutulur; kalıcı depolama ve gerçek emir yoktur.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Position:
    """Tek bir varlık pozisyonu."""

    symbol: str
    quantity: float = 0.0
    avg_price: float = 0.0

    def market_value(self, price: float) -> float:
        """Verilen fiyata göre pozisyonun piyasa değeri."""
        return self.quantity * price


@dataclass
class Portfolio:
    """Paper-trading portföyü."""

    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    realized_pnl: float = 0.0
    peak_equity: float = field(default=0.0)

    def __post_init__(self) -> None:
        if self.cash < 0:
            raise ValueError("Başlangıç nakiti negatif olamaz.")
        if self.peak_equity <= 0:
            self.peak_equity = self.cash

    def equity(self, prices: dict[str, float]) -> float:
        """Nakit + tüm pozisyonların piyasa değeri."""
        holdings = sum(
            pos.market_value(prices.get(sym, pos.avg_price)) for sym, pos in self.positions.items()
        )
        return self.cash + holdings

    def asset_value(self, symbol: str, price: float) -> float:
        """Belirli bir varlığın güncel piyasa değeri."""
        pos = self.positions.get(symbol)
        return pos.market_value(price) if pos else 0.0

    def drawdown(self, prices: dict[str, float]) -> float:
        """Tepe özkaynağa göre güncel düşüş oranı (0-1)."""
        current = self.equity(prices)
        self.peak_equity = max(self.peak_equity, current)
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - current) / self.peak_equity)

    def apply_fill(self, symbol: str, quantity: float, price: float) -> None:
        """Bir emrin gerçekleşmesini (fill) portföye uygular.

        ``quantity`` pozitif ise alış, negatif ise satış. Nakit ve ortalama
        maliyet buna göre güncellenir.
        """
        if price <= 0:
            raise ValueError("Fiyat pozitif olmalı.")
        if quantity == 0:
            raise ValueError("Miktar sıfır olamaz.")

        cost = quantity * price
        if quantity > 0 and cost > self.cash:
            raise ValueError("Yetersiz nakit.")

        pos = self.positions.get(symbol, Position(symbol=symbol))

        if quantity > 0:
            # Alış: ağırlıklı ortalama maliyet güncellenir.
            total_qty = pos.quantity + quantity
            pos.avg_price = (pos.avg_price * pos.quantity + price * quantity) / total_qty
            pos.quantity = total_qty
        else:
            sell_qty = -quantity
            if sell_qty > pos.quantity:
                raise ValueError("Açığa satış bu iskelet sürümde desteklenmez.")
            # Satış: gerçekleşmiş kâr/zarar kaydedilir.
            self.realized_pnl += (price - pos.avg_price) * sell_qty
            pos.quantity -= sell_qty

        self.cash -= cost

        if pos.quantity == 0:
            self.positions.pop(symbol, None)
        else:
            self.positions[symbol] = pos
