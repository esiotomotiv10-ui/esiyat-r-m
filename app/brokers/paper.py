"""Paper (kağıt üzerinde) broker uygulaması.

Emirleri gerçek piyasaya göndermez; referans fiyattan anında gerçekleşmiş
sayar. Kill switch etkinse hiçbir emri kabul etmez.
"""

from __future__ import annotations

import uuid

from app.brokers.base import BrokerClient, Order, OrderResult, OrderType
from app.core.kill_switch import KillSwitch, kill_switch


class PaperBroker(BrokerClient):
    """Bellek içi paper-trading broker'ı."""

    is_paper = True

    def __init__(self, *, switch: KillSwitch | None = None) -> None:
        self._kill_switch = switch or kill_switch

    def submit_order(self, order: Order, *, reference_price: float) -> OrderResult:
        if self._kill_switch.is_engaged:
            return OrderResult(
                accepted=False,
                order_id=None,
                filled_quantity=0.0,
                avg_fill_price=0.0,
                is_paper=True,
                message="Kill switch etkin — emir reddedildi.",
            )
        if reference_price <= 0:
            return OrderResult(
                accepted=False,
                order_id=None,
                filled_quantity=0.0,
                avg_fill_price=0.0,
                is_paper=True,
                message="Geçersiz referans fiyat.",
            )

        # Limit emirlerde gerçekleşme fiyatı limit ile sınırlanır.
        fill_price = reference_price
        if order.order_type is OrderType.LIMIT and order.limit_price is not None:
            fill_price = order.limit_price

        return OrderResult(
            accepted=True,
            order_id=str(uuid.uuid4()),
            filled_quantity=order.quantity,
            avg_fill_price=fill_price,
            is_paper=True,
            message="Paper emir gerçekleşti (simülasyon).",
        )

    def cancel_order(self, order_id: str) -> bool:
        # Paper emirler anında gerçekleştiği için bekleyen emir yoktur.
        return False
