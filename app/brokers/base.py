"""Broker istemci arayüzü ve emir modelleri.

Bu iskelet sürümde yalnızca arayüz ve paper (kağıt üzerinde) uygulaması
bulunur. Gerçek broker istemcileri bu soyut arayüzü uygulamalıdır ancak
gerçek emir gönderimi güvenlik kuralları gereği kapalıdır.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite


class OrderSide(StrEnum):
    """Emir yönü."""

    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    """Emir tipi."""

    MARKET = "market"
    LIMIT = "limit"


@dataclass(frozen=True)
class Order:
    """Bir emir talebi."""

    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("Emir sembolü boş olamaz.")
        if not isfinite(self.quantity) or self.quantity <= 0:
            raise ValueError("Emir miktarı pozitif olmalı.")
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError("Limit emir için limit_price gerekli.")
        if self.limit_price is not None and (
            not isfinite(self.limit_price) or self.limit_price <= 0
        ):
            raise ValueError("Limit fiyat pozitif ve sonlu olmalı.")


@dataclass(frozen=True)
class OrderResult:
    """Bir emrin sonucu."""

    accepted: bool
    order_id: str | None
    filled_quantity: float
    avg_fill_price: float
    is_paper: bool
    message: str


class BrokerClient(ABC):
    """Broker istemcileri için soyut arayüz."""

    is_paper: bool

    @abstractmethod
    def submit_order(self, order: Order, *, reference_price: float) -> OrderResult:
        """Bir emri gönderir.

        Gerçek broker uygulamaları, ``core.config.Settings`` kurallarına uymak
        zorundadır: paper dışı mod ve canlı emir gönderimi kapalıdır.
        """

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Bekleyen bir emri iptal eder."""
