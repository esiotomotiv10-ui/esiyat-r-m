"""RSI aşırı alım / aşırı satım stratejisi.

RSI aşırı satım eşiğinin altındaysa alış, aşırı alım eşiğinin üstündeyse satış
sinyali üretir. Sinyal gücü, eşikten uzaklıkla orantılıdır.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from app.indicators import rsi
from app.strategies._util import all_finite, clamp01
from app.strategies.base import Signal, SignalType, Strategy


class RSIStrategy(Strategy):
    """Göreceli Güç Endeksi tabanlı aşırı alım/satım stratejisi."""

    name = "rsi"

    def __init__(
        self,
        period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
    ) -> None:
        if period <= 0:
            raise ValueError("period pozitif olmalı.")
        if not 0.0 < oversold < overbought < 100.0:
            raise ValueError("0 < oversold < overbought < 100 olmalı.")
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    @property
    def min_bars(self) -> int:
        return self.period + 1

    def generate(self, symbol: str, closes: Sequence[float]) -> Signal:
        if len(closes) < self.min_bars or not all_finite(closes):
            return Signal(symbol=symbol, type=SignalType.HOLD, strategy=self.name)

        value = float(rsi(closes, self.period)[-1])
        if math.isnan(value):
            return Signal(symbol=symbol, type=SignalType.HOLD, strategy=self.name)

        if value <= self.oversold:
            strength = clamp01((self.oversold - value) / self.oversold)
            return Signal(
                symbol=symbol,
                type=SignalType.BUY,
                strength=strength,
                reason=f"RSI aşırı satım bölgesinde ({value:.1f} <= {self.oversold:.0f}).",
                strategy=self.name,
            )
        if value >= self.overbought:
            strength = clamp01((value - self.overbought) / (100.0 - self.overbought))
            return Signal(
                symbol=symbol,
                type=SignalType.SELL,
                strength=strength,
                reason=f"RSI aşırı alım bölgesinde ({value:.1f} >= {self.overbought:.0f}).",
                strategy=self.name,
            )
        return Signal(symbol=symbol, type=SignalType.HOLD, strategy=self.name)
