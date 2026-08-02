"""EMA kesişim stratejisi.

Kısa dönem EMA, uzun dönem EMA'yı yukarı keserse alış; aşağı keserse satış.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from app.indicators import ema
from app.strategies._util import all_finite
from app.strategies.base import Signal, SignalType, Strategy


class EMACrossoverStrategy(Strategy):
    """Üstel hareketli ortalama kesişim stratejisi."""

    name = "ema_crossover"

    def __init__(self, short_period: int = 12, long_period: int = 26) -> None:
        if not (0 < short_period < long_period):
            raise ValueError("short_period, long_period'dan küçük ve pozitif olmalı.")
        self.short_period = short_period
        self.long_period = long_period

    @property
    def min_bars(self) -> int:
        return self.long_period + 1

    def generate(self, symbol: str, closes: Sequence[float]) -> Signal:
        if len(closes) < self.min_bars or not all_finite(closes):
            return Signal(symbol=symbol, type=SignalType.HOLD, strategy=self.name)

        short = ema(closes, self.short_period)
        long = ema(closes, self.long_period)

        prev_short, prev_long = short[-2], long[-2]
        curr_short, curr_long = short[-1], long[-1]
        if any(math.isnan(x) for x in (prev_short, prev_long, curr_short, curr_long)):
            return Signal(symbol=symbol, type=SignalType.HOLD, strategy=self.name)

        crossed_up = prev_short <= prev_long and curr_short > curr_long
        crossed_down = prev_short >= prev_long and curr_short < curr_long

        if crossed_up:
            return Signal(
                symbol=symbol,
                type=SignalType.BUY,
                strength=1.0,
                reason="Kısa EMA uzun EMA'yı yukarı kesti.",
                strategy=self.name,
            )
        if crossed_down:
            return Signal(
                symbol=symbol,
                type=SignalType.SELL,
                strength=1.0,
                reason="Kısa EMA uzun EMA'yı aşağı kesti.",
                strategy=self.name,
            )
        return Signal(symbol=symbol, type=SignalType.HOLD, strategy=self.name)
