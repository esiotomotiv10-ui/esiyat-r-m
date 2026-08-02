"""Strateji arayüzü ve teknik analiz sinyal modeli.

Sinyal modeli immutable'dır ve geçersiz (NaN/inf, aralık dışı) güç değerlerini
reddeder. Strateji arayüzü yalnızca geçmiş ve mevcut kapanışları alır; gelecek
barlara erişim yoktur (look-ahead bias engellenir) ve aynı girdi aynı sonucu
üretir (deterministik).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite


class SignalType(StrEnum):
    """Sinyal tipleri."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass(frozen=True)
class Signal:
    """Bir strateji tarafından üretilen, immutable teknik analiz sinyali.

    ``strength`` 0 ile 1 arasında olmalıdır. NaN/inf veya aralık dışı güç
    değerleri reddedilir.
    """

    symbol: str
    type: SignalType
    strength: float = 0.0
    reason: str = ""
    strategy: str = ""
    timestamp: datetime | None = None

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("Sinyal sembolü boş olamaz.")
        if not isinstance(self.type, SignalType):
            raise ValueError("Sinyal tipi geçersiz.")
        if not isfinite(self.strength):
            raise ValueError("Sinyal gücü sonlu olmalı (NaN/inf reddedilir).")
        if not 0.0 <= self.strength <= 1.0:
            raise ValueError("Sinyal gücü 0 ile 1 arasında olmalı.")


class Strategy(ABC):
    """Tüm stratejiler için soyut arayüz.

    Sözleşme:
    - ``generate`` yalnızca geçmiş ve mevcut kapanışları alır (dizinin son
      elemanı mevcut bardır); gelecek barlara erişim yoktur.
    - Yetersiz veri durumunda ``HOLD`` döndürülür.
    - Aynı girdi her zaman aynı sinyali üretir (deterministik).
    """

    name: str

    @property
    def min_bars(self) -> int:
        """Anlamlı sinyal için gereken asgari bar sayısı (varsayılan 1)."""
        return 1

    @abstractmethod
    def generate(self, symbol: str, closes: Sequence[float]) -> Signal:
        """Kapanış fiyatı serisinden bir sinyal üretir."""
