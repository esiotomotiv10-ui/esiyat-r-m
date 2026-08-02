"""Paper trading orchestrator.

Bir ``BarSeries`` üzerinde bar-by-bar çalışır: her barda ``SignalEngine`` ile
birleşik sinyal üretir ve kararı **bir sonraki barın açılış (open) fiyatında**
``ExecutionEngine`` üzerinden gerçekleştirir. Böylece look-ahead bias oluşmaz.

Güvenlik güvenceleri:
- Yalnızca yerleşik ``PaperBroker`` kullanılır (gerçek broker/emir yoktur).
- Global kill switch ve mevcut ``RiskManager`` korumaları uygulanır.
- Short selling kapalıdır; yetersiz nakit ve fazla satış reddedilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite

from app.brokers.base import Order, OrderSide
from app.brokers.paper import PaperBroker
from app.execution.engine import ExecutionEngine
from app.market_data.models import BarSeries
from app.paper_trading.result import (
    AcceptedOrder,
    EquityPoint,
    GeneratedSignal,
    PaperTradingResult,
    RejectedOrder,
)
from app.portfolio.portfolio import Portfolio
from app.risk.limits import RiskManager
from app.signals.engine import SignalEngine
from app.strategies.base import SignalType

# Pozisyon boyutunu risk bütçesinin biraz altında tutan güvenlik tamponu.
_SIZING_BUFFER = 0.99


@dataclass(frozen=True)
class OrchestratorConfig:
    """Paper trading orchestrator yapılandırması."""

    initial_cash: float = 100_000.0
    commission_rate: float = 0.0
    slippage_rate: float = 0.0
    # Pozisyon boyutlandırmada kullanılan stop mesafesi (giriş fiyatına oran).
    stop_loss_pct: float = 0.15

    def __post_init__(self) -> None:
        if not isfinite(self.initial_cash) or self.initial_cash <= 0:
            raise ValueError("initial_cash pozitif ve sonlu olmalı.")
        if not isfinite(self.commission_rate) or not 0.0 <= self.commission_rate < 1.0:
            raise ValueError("commission_rate [0, 1) aralığında olmalı.")
        if not isfinite(self.slippage_rate) or not 0.0 <= self.slippage_rate < 1.0:
            raise ValueError("slippage_rate [0, 1) aralığında olmalı.")
        if not 0.0 < self.stop_loss_pct < 1.0:
            raise ValueError("stop_loss_pct (0, 1) aralığında olmalı.")

    def buy_fill_price(self, open_price: float) -> float:
        """Alışta slippage ve komisyonu içeren efektif gerçekleşme fiyatı."""
        return open_price * (1.0 + self.slippage_rate) * (1.0 + self.commission_rate)

    def sell_fill_price(self, open_price: float) -> float:
        """Satışta slippage ve komisyonu içeren efektif gerçekleşme fiyatı."""
        return open_price * (1.0 - self.slippage_rate) * (1.0 - self.commission_rate)


@dataclass
class PaperTradingOrchestrator:
    """SignalEngine + ExecutionEngine'i paper modda birbirine bağlayan motor."""

    signal_engine: SignalEngine
    config: OrchestratorConfig = field(default_factory=OrchestratorConfig)
    risk_manager: RiskManager | None = None

    def run(self, series: BarSeries) -> PaperTradingResult:
        """Stratejileri seri üzerinde bar-by-bar paper modda çalıştırır."""
        # Mevcut RiskManager ve global kill switch kullanılır (ExecutionEngine
        # ve PaperBroker varsayılan olarak global kill switch'e bağlıdır).
        portfolio = Portfolio(cash=self.config.initial_cash)
        risk_manager = self.risk_manager or RiskManager()
        engine = ExecutionEngine(
            portfolio=portfolio,
            risk_manager=risk_manager,
            broker=PaperBroker(),
        )

        symbol = series.symbol
        closes = [bar.close for bar in series]

        signals: list[GeneratedSignal] = []
        accepted: list[AcceptedOrder] = []
        rejected: list[RejectedOrder] = []
        equity_curve: list[EquityPoint] = []

        pending: SignalType | None = None

        for i, bar in enumerate(series):
            # 1) Önceki barda alınan kararı bu barın açılış fiyatında işle.
            if pending is SignalType.BUY:
                self._process_buy(
                    engine, risk_manager, symbol, bar.open, bar.timestamp, accepted, rejected
                )
            elif pending is SignalType.SELL:
                self._process_sell(
                    engine, portfolio, symbol, bar.open, bar.timestamp, accepted, rejected
                )
            pending = None

            # 2) Bu barda sinyal üret (yalnızca i'ye kadar olan kapanışlar).
            combined = self.signal_engine.evaluate(symbol, closes[: i + 1], timestamp=bar.timestamp)
            signals.append(GeneratedSignal(timestamp=bar.timestamp, signal=combined.signal))

            # 3) Bir sonraki bar için kararı belirle.
            held = self._held(portfolio, symbol)
            if combined.signal.type is SignalType.BUY and held == 0.0:
                pending = SignalType.BUY
            elif combined.signal.type is SignalType.SELL:
                pending = SignalType.SELL

            equity_curve.append(
                EquityPoint(timestamp=bar.timestamp, equity=portfolio.equity({symbol: bar.close}))
            )

        final_price = closes[-1]
        positions = tuple(sorted((sym, pos.quantity) for sym, pos in portfolio.positions.items()))
        return PaperTradingResult(
            symbol=symbol,
            initial_cash=self.config.initial_cash,
            ending_cash=portfolio.cash,
            final_equity=portfolio.equity({symbol: final_price}),
            positions=positions,
            signals=tuple(signals),
            accepted_orders=tuple(accepted),
            rejected_orders=tuple(rejected),
            equity_curve=tuple(equity_curve),
        )

    @staticmethod
    def _held(portfolio: Portfolio, symbol: str) -> float:
        pos = portfolio.positions.get(symbol)
        return pos.quantity if pos else 0.0

    def _process_buy(
        self,
        engine: ExecutionEngine,
        risk_manager: RiskManager,
        symbol: str,
        open_price: float,
        timestamp: datetime,
        accepted: list[AcceptedOrder],
        rejected: list[RejectedOrder],
    ) -> None:
        fill_price = self.config.buy_fill_price(open_price)
        stop_price = fill_price * (1.0 - self.config.stop_loss_pct)
        raw_qty = risk_manager.position_size(
            equity=engine.portfolio.equity({symbol: fill_price}),
            entry_price=fill_price,
            stop_price=stop_price,
        )
        quantity = raw_qty * _SIZING_BUFFER
        if not isfinite(quantity) or quantity <= 0:
            rejected.append(
                RejectedOrder(timestamp, OrderSide.BUY, quantity, "Hesaplanan miktar geçersiz.")
            )
            return
        order = Order(symbol=symbol, side=OrderSide.BUY, quantity=quantity)
        report = engine.execute(order, reference_price=fill_price, stop_price=stop_price)
        if report.executed and report.order_result is not None:
            accepted.append(
                AcceptedOrder(
                    timestamp,
                    OrderSide.BUY,
                    report.order_result.filled_quantity,
                    report.order_result.avg_fill_price,
                )
            )
        else:
            rejected.append(RejectedOrder(timestamp, OrderSide.BUY, quantity, report.reason))

    def _process_sell(
        self,
        engine: ExecutionEngine,
        portfolio: Portfolio,
        symbol: str,
        open_price: float,
        timestamp: datetime,
        accepted: list[AcceptedOrder],
        rejected: list[RejectedOrder],
    ) -> None:
        held = self._held(portfolio, symbol)
        if held <= 0.0:
            # Short selling kapalı: elde pozisyon yokken satış reddedilir.
            rejected.append(
                RejectedOrder(
                    timestamp, OrderSide.SELL, 0.0, "Short selling kapalı — satış reddedildi."
                )
            )
            return
        fill_price = self.config.sell_fill_price(open_price)
        order = Order(symbol=symbol, side=OrderSide.SELL, quantity=held)
        report = engine.execute(order, reference_price=fill_price, stop_price=fill_price)
        if report.executed and report.order_result is not None:
            accepted.append(
                AcceptedOrder(
                    timestamp,
                    OrderSide.SELL,
                    report.order_result.filled_quantity,
                    report.order_result.avg_fill_price,
                )
            )
        else:
            rejected.append(RejectedOrder(timestamp, OrderSide.SELL, held, report.reason))
