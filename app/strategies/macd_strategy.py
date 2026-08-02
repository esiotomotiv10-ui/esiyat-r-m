"""MACD kesişim stratejisi.

MACD çizgisi sinyal çizgisini yukarı keserse (histogram negatiften pozitife)
alış; aşağı keserse (pozitiften negatife) satış sinyali üretir.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from app.indicators import macd
from app.strategies._util import all_finite
from app.strategies.base import Signal, SignalType, Strategy


class MACDCrossoverStrategy(Strategy):
    """MACD/sinyal çizgisi kesişim stratejisi."""

    name = "macd_crossover"

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ) -> None:
        if not (0 < fast_period < slow_period):
            raise ValueError("fast_period, slow_period'dan küçük ve pozitif olmalı.")
        if signal_period <= 0:
            raise ValueError("signal_period pozitif olmalı.")
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period

    @property
    def min_bars(self) -> int:
        # MACD çizgisi slow_period'dan itibaren, sinyal çizgisi ise ek
        # signal_period gözlem sonrası oluşur; iki geçerli histogram gerekir.
        return self.slow_period + self.signal_period + 1

    def generate(self, symbol: str, closes: Sequence[float]) -> Signal:
        if len(closes) < self.min_bars or not all_finite(closes):
            return Signal(symbol=symbol, type=SignalType.HOLD, strategy=self.name)

        result = macd(closes, self.fast_period, self.slow_period, self.signal_period)
        prev, curr = result.histogram[-2], result.histogram[-1]
        if math.isnan(prev) or math.isnan(curr):
            return Signal(symbol=symbol, type=SignalType.HOLD, strategy=self.name)

        if prev <= 0.0 < curr:
            return Signal(
                symbol=symbol,
                type=SignalType.BUY,
                strength=1.0,
                reason="MACD sinyal çizgisini yukarı kesti.",
                strategy=self.name,
            )
        if prev >= 0.0 > curr:
            return Signal(
                symbol=symbol,
                type=SignalType.SELL,
                strength=1.0,
                reason="MACD sinyal çizgisini aşağı kesti.",
                strategy=self.name,
            )
        return Signal(symbol=symbol, type=SignalType.HOLD, strategy=self.name)
