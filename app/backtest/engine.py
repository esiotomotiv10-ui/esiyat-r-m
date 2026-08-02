"""Backtest motoru.

Bir stratejiyi geçmiş mum serisi üzerinde mum-mum çalıştırır. Tüm işlemler
yerleşik ``PaperBroker`` ve ``ExecutionEngine`` üzerinden yürütülür; böylece
risk limitleri ve paper-only güvenlik güvenceleri backtest'te de geçerlidir.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.backtest.result import BacktestResult, EquityPoint, Trade
from app.brokers.base import Order, OrderSide, OrderType
from app.brokers.paper import PaperBroker
from app.core.kill_switch import KillSwitch
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

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise ValueError("initial_cash pozitif olmalı.")
        if not 0 < self.stop_loss_pct < 1:
            raise ValueError("stop_loss_pct (0, 1) aralığında olmalı.")
        if self.warmup < 0:
            raise ValueError("warmup negatif olamaz.")


@dataclass
class BacktestEngine:
    """Tek varlık için mum-mum backtest motoru."""

    strategy: Strategy
    config: BacktestConfig = field(default_factory=BacktestConfig)
    risk_manager: RiskManager | None = None

    def run(self, series: BarSeries) -> BacktestResult:
        """Stratejiyi seri üzerinde çalıştırıp sonucu döndürür."""
        # Backtest'in gerçek kill switch durumundan bağımsız olması için
        # yerel (kapalı) bir kill switch örneği kullanılır.
        switch = KillSwitch()
        portfolio = Portfolio(cash=self.config.initial_cash)
        risk_manager = self.risk_manager or RiskManager(switch=switch)
        engine = ExecutionEngine(
            portfolio=portfolio,
            risk_manager=risk_manager,
            broker=PaperBroker(switch=switch),
            switch=switch,
        )

        symbol = series.symbol
        closes = [bar.close for bar in series]
        trades: list[Trade] = []
        equity_curve: list[EquityPoint] = []

        for i, bar in enumerate(series):
            price = bar.close

            if i >= self.config.warmup:
                window = closes[: i + 1]
                signal = self.strategy.generate(symbol, window)
                position = portfolio.positions.get(symbol)
                held = position.quantity if position else 0.0

                if signal.type is SignalType.BUY and held == 0.0:
                    stop_price = price * (1.0 - self.config.stop_loss_pct)
                    raw_qty = risk_manager.position_size(
                        equity=portfolio.equity({symbol: price}),
                        entry_price=price,
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
                        report = engine.execute(order, reference_price=price, stop_price=stop_price)
                        if report.executed and report.order_result is not None:
                            trades.append(
                                Trade(
                                    timestamp=bar.timestamp,
                                    symbol=symbol,
                                    side=OrderSide.BUY,
                                    quantity=report.order_result.filled_quantity,
                                    price=report.order_result.avg_fill_price,
                                )
                            )

                elif signal.type is SignalType.SELL and held > 0.0:
                    order = Order(
                        symbol=symbol,
                        side=OrderSide.SELL,
                        quantity=held,
                        order_type=OrderType.MARKET,
                    )
                    report = engine.execute(order, reference_price=price, stop_price=price)
                    if report.executed and report.order_result is not None:
                        trades.append(
                            Trade(
                                timestamp=bar.timestamp,
                                symbol=symbol,
                                side=OrderSide.SELL,
                                quantity=report.order_result.filled_quantity,
                                price=report.order_result.avg_fill_price,
                            )
                        )

            equity_curve.append(
                EquityPoint(timestamp=bar.timestamp, equity=portfolio.equity({symbol: price}))
            )

        final_price = closes[-1]
        return BacktestResult(
            symbol=symbol,
            initial_equity=self.config.initial_cash,
            final_equity=portfolio.equity({symbol: final_price}),
            equity_curve=tuple(equity_curve),
            trades=tuple(trades),
        )
