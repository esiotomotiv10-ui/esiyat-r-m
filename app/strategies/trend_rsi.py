"""Trend + RSI birleşik stratejisi.

Uzun dönem SMA'ya göre trend yönü belirlenir; RSI ile giriş zamanlaması
yapılır. Yukarı trendde RSI görece düşükken (geri çekilme) alış; aşağı trendde
RSI görece yüksekken (tepki yükselişi) satış sinyali üretilir.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from app.indicators import rsi, sma
from app.strategies._util import all_finite, clamp01
from app.strategies.base import Signal, SignalType, Strategy


class TrendRSIStrategy(Strategy):
    """Trend filtresi ile RSI zamanlamasını birleştiren strateji."""

    name = "trend_rsi"

    def __init__(
        self,
        trend_period: int = 50,
        rsi_period: int = 14,
        rsi_buy_below: float = 40.0,
        rsi_sell_above: float = 60.0,
    ) -> None:
        if trend_period <= 0 or rsi_period <= 0:
            raise ValueError("trend_period ve rsi_period pozitif olmalı.")
        if not 0.0 < rsi_buy_below < rsi_sell_above < 100.0:
            raise ValueError("0 < rsi_buy_below < rsi_sell_above < 100 olmalı.")
        self.trend_period = trend_period
        self.rsi_period = rsi_period
        self.rsi_buy_below = rsi_buy_below
        self.rsi_sell_above = rsi_sell_above

    @property
    def min_bars(self) -> int:
        return max(self.trend_period, self.rsi_period + 1)

    def generate(self, symbol: str, closes: Sequence[float]) -> Signal:
        if len(closes) < self.min_bars or not all_finite(closes):
            return Signal(symbol=symbol, type=SignalType.HOLD, strategy=self.name)

        trend = float(sma(closes, self.trend_period)[-1])
        rsi_value = float(rsi(closes, self.rsi_period)[-1])
        price = float(closes[-1])
        if math.isnan(trend) or math.isnan(rsi_value):
            return Signal(symbol=symbol, type=SignalType.HOLD, strategy=self.name)

        uptrend = price > trend
        downtrend = price < trend

        if uptrend and rsi_value <= self.rsi_buy_below:
            strength = clamp01((self.rsi_buy_below - rsi_value) / self.rsi_buy_below)
            return Signal(
                symbol=symbol,
                type=SignalType.BUY,
                strength=strength,
                reason=(f"Yukarı trend (fiyat>{trend:.2f}) ve RSI düşük ({rsi_value:.1f})."),
                strategy=self.name,
            )
        if downtrend and rsi_value >= self.rsi_sell_above:
            strength = clamp01((rsi_value - self.rsi_sell_above) / (100.0 - self.rsi_sell_above))
            return Signal(
                symbol=symbol,
                type=SignalType.SELL,
                strength=strength,
                reason=(f"Aşağı trend (fiyat<{trend:.2f}) ve RSI yüksek ({rsi_value:.1f})."),
                strategy=self.name,
            )
        return Signal(symbol=symbol, type=SignalType.HOLD, strategy=self.name)
