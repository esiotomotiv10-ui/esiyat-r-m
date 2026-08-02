"""Piyasa verisi alan modelleri (domain models).

``Bar`` (bkz. ``app.market_data.base``) tek bir OHLCV mumunu temsil eder.
Bu modül, doğrulanmış ve sıralı bir mum serisini (``BarSeries``) ve zaman
dilimi (``Timeframe``) tanımını sağlar. Backtest ve gösterge hesaplamaları
bu seriler üzerinden çalışır.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

import numpy as np
from numpy.typing import NDArray

from app.market_data.base import Bar

FloatArray = NDArray[np.float64]


class Timeframe(StrEnum):
    """Desteklenen mum zaman dilimleri."""

    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"


def _validate_bar(bar: Bar) -> None:
    """Tek bir mumun tutarlılığını doğrular."""
    values = (bar.open, bar.high, bar.low, bar.close, bar.volume)
    if not all(isfinite(v) for v in values):
        raise ValueError(f"{bar.symbol}: mum değerleri sonlu olmalı.")
    if min(bar.open, bar.high, bar.low, bar.close) <= 0:
        raise ValueError(f"{bar.symbol}: fiyatlar pozitif olmalı.")
    if bar.volume < 0:
        raise ValueError(f"{bar.symbol}: hacim negatif olamaz.")
    if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close):
        raise ValueError(f"{bar.symbol}: OHLC tutarsız (high/low aralığı hatalı).")


@dataclass(frozen=True)
class BarSeries:
    """Tek bir sembole ait, zamana göre sıralı doğrulanmış mum serisi."""

    symbol: str
    timeframe: Timeframe
    bars: tuple[Bar, ...]

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("Sembol boş olamaz.")
        if not self.bars:
            raise ValueError("Mum serisi boş olamaz.")
        prev_ts = None
        for bar in self.bars:
            if bar.symbol != self.symbol:
                raise ValueError(
                    f"Mum sembolü ({bar.symbol}) seri sembolü ({self.symbol}) ile uyuşmuyor."
                )
            _validate_bar(bar)
            if prev_ts is not None and bar.timestamp <= prev_ts:
                raise ValueError("Mumlar zamana göre artan sırada ve tekil olmalı.")
            prev_ts = bar.timestamp

    def __len__(self) -> int:
        return len(self.bars)

    def __iter__(self) -> Iterator[Bar]:
        return iter(self.bars)

    def __getitem__(self, index: int) -> Bar:
        return self.bars[index]

    @property
    def closes(self) -> FloatArray:
        """Kapanış fiyatları dizisi."""
        return np.array([b.close for b in self.bars], dtype=np.float64)

    @property
    def highs(self) -> FloatArray:
        """En yüksek fiyatlar dizisi."""
        return np.array([b.high for b in self.bars], dtype=np.float64)

    @property
    def lows(self) -> FloatArray:
        """En düşük fiyatlar dizisi."""
        return np.array([b.low for b in self.bars], dtype=np.float64)

    @property
    def opens(self) -> FloatArray:
        """Açılış fiyatları dizisi."""
        return np.array([b.open for b in self.bars], dtype=np.float64)

    @property
    def volumes(self) -> FloatArray:
        """Hacim dizisi."""
        return np.array([b.volume for b in self.bars], dtype=np.float64)

    @classmethod
    def from_bars(cls, symbol: str, timeframe: Timeframe, bars: Sequence[Bar]) -> BarSeries:
        """Bir mum dizisinden doğrulanmış seri oluşturur."""
        return cls(symbol=symbol, timeframe=timeframe, bars=tuple(bars))
