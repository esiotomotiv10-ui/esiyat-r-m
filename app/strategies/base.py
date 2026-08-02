"""Strateji arayüzü ve sinyal modelleri."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum


class SignalType(StrEnum):
    """Sinyal tipleri."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass(frozen=True)
class Signal:
    """Bir strateji tarafından üretilen işlem sinyali."""

    symbol: str
    type: SignalType
    strength: float = 0.0  # 0-1 arası güven/şiddet


class Strategy(ABC):
    """Tüm stratejiler için soyut arayüz."""

    name: str

    @abstractmethod
    def generate(self, symbol: str, closes: Sequence[float]) -> Signal:
        """Kapanış fiyatı serisinden bir sinyal üretir."""
