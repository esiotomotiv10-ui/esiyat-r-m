"""Backtest motoru.

Bir stratejiyi geçmiş mum serisi üzerinde mum-mum çalıştırır. Tüm işlemler
yerleşik ``PaperBroker`` ve ``ExecutionEngine`` üzerinden yürütülür; böylece
risk limitleri ve paper-only güvenlik güvenceleri backtest'te de geçerlidir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite

from app.backtest.result import BacktestResult, EquityPoint, Trade
from app.brokers.base import Order, OrderSide, OrderType
from app.brokers.paper import PaperBroker
from app.execution.engine import ExecutionEngine
from app.market_data.models import BarSeries
from app.portfolio.portfolio import Portfolio
from app.risk.limits import RiskManager
from app.strategies.base import SignalType, Strategy

# Pozisyon boyutunu risk bütçesinin biraz altında tutan güvenlik tamponu.
_SIZING_BUFFER = 0.99


@dataclass(frozen=True)
class BacktestConfig:
    """Backtest yapılandırması."""

    initial_cash: float = 100_000.0
    # Pozisyon boyutlandırmada kullanılan stop mesafesi (giriş fiyatına oran).
    # %10'un altında notional için >= 0.10 seçilir (varlık ağırlığı limiti).
    stop_loss_pct: float = 0.15
    # İşleme başlamadan önce beklenecek asgari mum sayısı.
    warmup: int = 0
    commission_rate: float = 0.0
    slippage_rate: float = 0.0

    def __post_init__(self) -> None:
        if not isfinite(self.initial_cash) or self.initial_cash <= 0:
            raise ValueError("initial_cash pozitif ve sonlu olmalı.")
        if not isfinite(self.stop_loss_pct) or not 0 < self.stop_loss_pct < 1:
            raise ValueError("stop_loss_pct (0, 1) aralığında olmalı.")
        if self.warmup < 0:
            raise ValueError("warmup negatif olamaz.")
        if not isfinite(self.commission_rate) or self.commission_rate < 0:
            raise ValueError("commission_rate negatif olmayan sonlu bir sayı olmalı.")
        if not isfinite(self.slippage_rate) or self.slippage_rate < 0:
            raise ValueError("slippage_rate negatif olmayan sonlu bir sayı olmalı.")
        if self.commission_rate + self.slippage_rate >= 1:
            raise ValueError("commission_rate + slippage_rate 1'den küçük olmalı.")


@dataclass
class BacktestEngine:
    """Tek varlık için mum-mum backtest motoru."""

    strategy: Strategy
    config: BacktestConfig = field(default_factory=BacktestConfig)
    risk_manager: RiskManager | None = None

    def run(self, series: BarSeries) -> BacktestResult:
        """Stratejiyi seri üzerinde çalıştırıp sonucu döndürür."""
        portfolio = Portfolio(cash=self.config.initial_cash)
        risk_manager = self.risk_manager or RiskManager()
        engine = ExecutionEngine(
            portfolio=portfolio,
            risk_manager=risk_manager,
            broker=PaperBroker(),
        )

        symbol = series.symbol
        closes = [bar.close for bar in series]
        trades: list[Trade] = []
        equity_curve: list[EquityPoint] = []
        open_lots: list[tuple[float, float]] = []
        pending_side: SignalType | None = None

        for i, bar in enumerate(series):
            if pending_side is SignalType.BUY:
                fill_price = self._effective_price(bar.open, OrderSide.BUY)
                stop_price = fill_price * (1.0 - self.config.stop_loss_pct)
                raw_qty = risk_manager.position_size(
                    equity=portfolio.equity({symbol: bar.open}),
                    entry_price=fill_price,
                    stop_price=stop_price,
                )
                # Risk bütçesinin tam sınırında kalmamak için küçük tampon.
                quantity = raw_qty * _SIZING_BUFFER
                if quantity > 0:
                    order = Order(
                        symbol=symbol,
                        side=OrderSide.BUY,
                        quantity=quantity,
                        order_type=OrderType.MARKET,
                    )
                    report = engine.execute(
                        order,
                        reference_price=fill_price,
                        stop_price=stop_price,
                    )
                    if report.executed and report.order_result is not None:
                        filled_qty = report.order_result.filled_quantity
                        filled_price = report.order_result.avg_fill_price
                        open_lots.append((filled_qty, filled_price))
                        trades.append(
                            Trade(
                                timestamp=bar.timestamp,
                                symbol=symbol,
                                side=OrderSide.BUY,
                                quantity=filled_qty,
                                price=filled_price,
                            )
                        )

            elif pending_side is SignalType.SELL:
                position = portfolio.positions.get(symbol)
                held = position.quantity if position else 0.0
                if held > 0.0:
                    fill_price = self._effective_price(bar.open, OrderSide.SELL)
                    order = Order(
                        symbol=symbol,
                        side=OrderSide.SELL,
                        quantity=held,
                        order_type=OrderType.MARKET,
                    )
                    report = engine.execute(
                        order, reference_price=fill_price, stop_price=fill_price
                    )
                    if report.executed and report.order_result is not None:
                        filled_qty = report.order_result.filled_quantity
                        filled_price = report.order_result.avg_fill_price
                        realized_pnl = self._realize_pnl(open_lots, filled_qty, filled_price)
                        trades.append(
                            Trade(
                                timestamp=bar.timestamp,
                                symbol=symbol,
                                side=OrderSide.SELL,
                                quantity=filled_qty,
                                price=filled_price,
                                realized_pnl=realized_pnl,
                            )
                        )

            pending_side = None

            equity_curve.append(
                EquityPoint(timestamp=bar.timestamp, equity=portfolio.equity({symbol: bar.close}))
            )

            if i >= self.config.warmup and i + 1 < len(series):
                window = closes[: i + 1]
                signal = self.strategy.generate(symbol, window)
                position = portfolio.positions.get(symbol)
                held = position.quantity if position else 0.0

                if signal.type is SignalType.BUY and held == 0.0:
                    pending_side = SignalType.BUY

                elif signal.type is SignalType.SELL and held > 0.0:
                    pending_side = SignalType.SELL

        final_price = closes[-1]
        return BacktestResult(
            symbol=symbol,
            initial_cash=self.config.initial_cash,
            ending_cash=portfolio.cash,
            final_equity=portfolio.equity({symbol: final_price}),
            equity_curve=tuple(equity_curve),
            trades=tuple(trades),
        )

    def _effective_price(self, open_price: float, side: OrderSide) -> float:
        """Komisyon ve slippage'i deterministik olarak fiyata uygular."""
        if not isfinite(open_price) or open_price <= 0:
            raise ValueError("open_price pozitif ve sonlu olmalı.")
        adjustment = self.config.commission_rate + self.config.slippage_rate
        if side is OrderSide.BUY:
            return open_price * (1.0 + adjustment)
        return open_price * (1.0 - adjustment)

    @staticmethod
    def _realize_pnl(
        open_lots: list[tuple[float, float]],
        sell_quantity: float,
        sell_price: float,
    ) -> float:
        """FIFO alış-satış eşleşmesine göre gerçekleşmiş PnL hesaplar."""
        remaining = sell_quantity
        realized = 0.0
        while remaining > 0 and open_lots:
            lot_quantity, lot_price = open_lots[0]
            matched = min(remaining, lot_quantity)
            realized += (sell_price - lot_price) * matched
            remaining -= matched
            lot_quantity -= matched
            if lot_quantity == 0:
                open_lots.pop(0)
            else:
                open_lots[0] = (lot_quantity, lot_price)
        if remaining > 1e-9:
            raise RuntimeError("Satış miktarı açık lotlardan büyük.")
        return realized
