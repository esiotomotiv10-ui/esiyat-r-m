"""SMA kesişim stratejisi (örnek).

Kısa dönem SMA, uzun dönem SMA'yı yukarı keserse alış; aşağı keserse satış
sinyali üretir. Bu yalnızca iskelet amaçlı örnek bir stratejidir.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from app.indicators import sma
from app.strategies.base import Signal, SignalType, Strategy


class SMACrossoverStrategy(Strategy):
    """Basit hareketli ortalama kesişim stratejisi."""

    name = "sma_crossover"

    def __init__(self, short_period: int = 20, long_period: int = 50) -> None:
        if not (0 < short_period < long_period):
            raise ValueError("short_period, long_period'dan küçük ve pozitif olmalı.")
        self.short_period = short_period
        self.long_period = long_period

    def generate(self, symbol: str, closes: Sequence[float]) -> Signal:
        if len(closes) < self.long_period + 1:
            return Signal(symbol=symbol, type=SignalType.HOLD)

        short = sma(closes, self.short_period)
        long = sma(closes, self.long_period)

        prev_short, prev_long = short[-2], long[-2]
        curr_short, curr_long = short[-1], long[-1]
        if any(math.isnan(x) for x in (prev_short, prev_long, curr_short, curr_long)):
            return Signal(symbol=symbol, type=SignalType.HOLD)

        crossed_up = prev_short <= prev_long and curr_short > curr_long
        crossed_down = prev_short >= prev_long and curr_short < curr_long

        if crossed_up:
            return Signal(symbol=symbol, type=SignalType.BUY, strength=1.0)
        if crossed_down:
            return Signal(symbol=symbol, type=SignalType.SELL, strength=1.0)
        return Signal(symbol=symbol, type=SignalType.HOLD)
