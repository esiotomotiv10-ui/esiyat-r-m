"""Emir yürütme motoru.

Bir emir talebini önce güvenlik (paper mod, kill switch), ardından risk
limitlerinden geçirir; onaylanırsa paper broker üzerinden gerçekleştirir ve
portföyü günceller. Gerçek emir gönderimi hiçbir koşulda yapılmaz.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.brokers.base import BrokerClient, Order, OrderResult, OrderSide
from app.brokers.paper import PaperBroker
from app.core.config import Settings, get_settings
from app.core.kill_switch import KillSwitch, kill_switch
from app.portfolio.portfolio import Portfolio
from app.risk.limits import RiskManager


@dataclass(frozen=True)
class ExecutionReport:
    """Bir emir yürütme denemesinin sonucu."""

    executed: bool
    reason: str
    order_result: OrderResult | None = None


class ExecutionEngine:
    """Güvenlik + risk + broker + portföyü birbirine bağlayan motor."""

    def __init__(
        self,
        *,
        portfolio: Portfolio,
        risk_manager: RiskManager | None = None,
        broker: BrokerClient | None = None,
        settings: Settings | None = None,
        switch: KillSwitch | None = None,
    ) -> None:
        self.portfolio = portfolio
        self.settings = settings or get_settings()
        self.risk_manager = risk_manager or RiskManager()
        self.broker = broker or PaperBroker()
        self._kill_switch = switch or kill_switch

        # Güvenlik güvencesi: yalnızca paper broker'a izin verilir.
        if not getattr(self.broker, "is_paper", False):
            raise RuntimeError(
                "Bu iskelet sürümde yalnızca paper broker desteklenir; "
                "gerçek emir gönderimi kapalıdır."
            )

    def execute(
        self,
        order: Order,
        *,
        reference_price: float,
        stop_price: float,
        daily_pnl: float = 0.0,
    ) -> ExecutionReport:
        """Bir emri güvenlik ve risk kontrollerinden geçirerek yürütür."""
        # 1) Kill switch ve canlı emir güvencesi.
        if self._kill_switch.is_engaged:
            return ExecutionReport(False, "Kill switch etkin — yürütme durduruldu.")
        if not self.settings.live_trading_disabled:
            # Yapılandırma bozulmuş olsa bile güvenli tarafta dur.
            return ExecutionReport(False, "Canlı emir kapalı olmalı — yürütme reddedildi.")

        # 2) Risk değerlendirmesi (yalnızca alışlar limit kontrolüne tabidir).
        prices = {order.symbol: reference_price}
        equity = self.portfolio.equity(prices)
        if order.side is OrderSide.BUY:
            decision = self.risk_manager.evaluate_trade(
                equity=equity,
                entry_price=reference_price,
                stop_price=stop_price,
                quantity=order.quantity,
                current_asset_value=self.portfolio.asset_value(order.symbol, reference_price),
                daily_pnl=daily_pnl,
                drawdown=self.portfolio.drawdown(prices),
            )
            if not decision.approved:
                return ExecutionReport(False, decision.reason)

        # 3) Paper broker üzerinden gerçekleştir.
        result = self.broker.submit_order(order, reference_price=reference_price)
        if not result.accepted:
            return ExecutionReport(False, result.message, order_result=result)

        # 4) Portföyü güncelle.
        signed_qty = result.filled_quantity
        if order.side is OrderSide.SELL:
            signed_qty = -signed_qty
        self.portfolio.apply_fill(order.symbol, signed_qty, result.avg_fill_price)

        return ExecutionReport(True, "Emir paper modda yürütüldü.", order_result=result)
