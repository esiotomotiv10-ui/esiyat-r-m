"""Stratejiler için ortak yardımcılar."""

from __future__ import annotations

from collections.abc import Sequence
from math import isfinite


def all_finite(closes: Sequence[float]) -> bool:
    """Tüm kapanışların sonlu (NaN/inf olmayan) olup olmadığını döndürür."""
    return all(isfinite(float(c)) for c in closes)


def clamp01(value: float) -> float:
    """Bir değeri [0, 1] aralığına kırpar."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value
