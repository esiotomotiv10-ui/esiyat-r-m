"""Backtest API endpoints.

The endpoint in this module is intentionally paper-only: callers provide local
OHLCV bars and strategy/config parameters, but cannot choose a broker, data
source, or execution mode.
"""

from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from app.backtest import BacktestConfig, BacktestEngine
from app.brokers.base import OrderSide
from app.market_data import Bar, BarSeries, Timeframe
from app.strategies import SMACrossoverStrategy

router = APIRouter(prefix="/backtests", tags=["backtests"])


def _ensure_finite(value: float, field_name: str) -> float:
    if not isfinite(value):
        raise ValueError(f"{field_name} sonlu bir sayı olmalı.")
    return value


class BarInput(BaseModel):
    """Single OHLCV bar supplied by an API caller."""

    timestamp: datetime
    open: float = Field(..., gt=0, allow_inf_nan=False)
    high: float = Field(..., gt=0, allow_inf_nan=False)
    low: float = Field(..., gt=0, allow_inf_nan=False)
    close: float = Field(..., gt=0, allow_inf_nan=False)
    volume: float = Field(..., ge=0, allow_inf_nan=False)

    @field_validator("open", "high", "low", "close", "volume")
    @classmethod
    def _finite_number(cls, value: float) -> float:
        return _ensure_finite(value, "bar değeri")

    def to_bar(self, symbol: str) -> Bar:
        """Convert API input to the domain Bar model."""
        return Bar(
            symbol=symbol,
            timestamp=self.timestamp,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
        )


class SMACrossoverStrategyInput(BaseModel):
    """Supported strategy configuration."""

    name: Literal["sma_crossover"] = "sma_crossover"
    short_period: int = Field(default=20, gt=0)
    long_period: int = Field(default=50, gt=0)

    @model_validator(mode="after")
    def _validate_periods(self) -> SMACrossoverStrategyInput:
        if self.short_period >= self.long_period:
            raise ValueError("short_period, long_period'dan küçük olmalı.")
        return self

    def to_strategy(self) -> SMACrossoverStrategy:
        """Create the domain strategy."""
        return SMACrossoverStrategy(
            short_period=self.short_period,
            long_period=self.long_period,
        )


class BacktestConfigInput(BaseModel):
    """Backtest configuration accepted by the API."""

    initial_cash: float = Field(default=100_000.0, gt=0, allow_inf_nan=False)
    stop_loss_pct: float = Field(default=0.15, gt=0, lt=1, allow_inf_nan=False)
    warmup: int = Field(default=0, ge=0)
    commission_rate: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    slippage_rate: float = Field(default=0.0, ge=0, allow_inf_nan=False)

    @field_validator("initial_cash", "stop_loss_pct", "commission_rate", "slippage_rate")
    @classmethod
    def _finite_number(cls, value: float) -> float:
        return _ensure_finite(value, "backtest config değeri")

    @model_validator(mode="after")
    def _validate_costs(self) -> BacktestConfigInput:
        if self.commission_rate + self.slippage_rate >= 1:
            raise ValueError("commission_rate + slippage_rate 1'den küçük olmalı.")
        return self

    def to_config(self) -> BacktestConfig:
        """Create the domain backtest config."""
        return BacktestConfig(
            initial_cash=self.initial_cash,
            stop_loss_pct=self.stop_loss_pct,
            warmup=self.warmup,
            commission_rate=self.commission_rate,
            slippage_rate=self.slippage_rate,
        )


class BacktestRequest(BaseModel):
    """Paper-only backtest request."""

    symbol: str = Field(..., min_length=1, max_length=32)
    timeframe: Timeframe = Timeframe.D1
    bars: list[BarInput] = Field(..., min_length=1)
    strategy: SMACrossoverStrategyInput
    config: BacktestConfigInput = Field(default_factory=BacktestConfigInput)

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        symbol = value.strip().upper()
        if not symbol:
            raise ValueError("symbol boş olamaz.")
        return symbol

    def to_series(self) -> BarSeries:
        """Create a validated domain BarSeries."""
        return BarSeries.from_bars(
            symbol=self.symbol,
            timeframe=self.timeframe,
            bars=[bar.to_bar(self.symbol) for bar in self.bars],
        )


class TradeResponse(BaseModel):
    """Single trade in a backtest response."""

    timestamp: datetime
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    realized_pnl: float
    notional: float


class EquityPointResponse(BaseModel):
    """Single equity curve point in a backtest response."""

    timestamp: datetime
    equity: float


class BacktestResponse(BaseModel):
    """Backtest response summary and full trace."""

    symbol: str
    initial_cash: float
    ending_cash: float
    final_equity: float
    total_return: float
    max_drawdown: float
    trade_count: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    equity_curve: list[EquityPointResponse]
    trades: list[TradeResponse]


@router.post("", response_model=BacktestResponse)
def run_backtest(request: BacktestRequest) -> BacktestResponse:
    """Run a paper-only backtest using caller-supplied bars."""
    try:
        result = BacktestEngine(
            request.strategy.to_strategy(),
            request.config.to_config(),
        ).run(request.to_series())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return BacktestResponse(
        symbol=result.symbol,
        initial_cash=result.initial_cash,
        ending_cash=result.ending_cash,
        final_equity=result.final_equity,
        total_return=result.total_return,
        max_drawdown=result.max_drawdown,
        trade_count=result.num_trades,
        winning_trades=result.winning_trades,
        losing_trades=result.losing_trades,
        win_rate=result.win_rate,
        equity_curve=[
            EquityPointResponse(timestamp=point.timestamp, equity=point.equity)
            for point in result.equity_curve
        ],
        trades=[
            TradeResponse(
                timestamp=trade.timestamp,
                symbol=trade.symbol,
                side=trade.side,
                quantity=trade.quantity,
                price=trade.price,
                realized_pnl=trade.realized_pnl,
                notional=trade.notional,
            )
            for trade in result.trades
        ],
    )
