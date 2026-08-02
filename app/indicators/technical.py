"""Teknik gösterge hesaplamaları.

Tüm fonksiyonlar saf (yan etkisiz) ve ``numpy`` tabanlıdır. Girdi olarak
sayısal diziler alır ve ``numpy.ndarray`` döndürür. Yetersiz veri için
ilgili konumlar ``numpy.nan`` ile doldurulur.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def _as_array(values: Sequence[float] | FloatArray) -> FloatArray:
    arr = np.asarray(values, dtype=np.float64)
    if arr.ndim != 1:
        raise ValueError("Girdi tek boyutlu bir dizi olmalı.")
    return arr


def sma(values: Sequence[float] | FloatArray, period: int) -> FloatArray:
    """Basit Hareketli Ortalama (Simple Moving Average)."""
    if period <= 0:
        raise ValueError("period pozitif olmalı.")
    arr = _as_array(values)
    out = np.full(arr.shape, np.nan, dtype=np.float64)
    if arr.size < period:
        return out
    cumsum = np.cumsum(np.insert(arr, 0, 0.0))
    out[period - 1 :] = (cumsum[period:] - cumsum[:-period]) / period
    return out


def ema(values: Sequence[float] | FloatArray, period: int) -> FloatArray:
    """Üstel Hareketli Ortalama (Exponential Moving Average)."""
    if period <= 0:
        raise ValueError("period pozitif olmalı.")
    arr = _as_array(values)
    out = np.full(arr.shape, np.nan, dtype=np.float64)
    if arr.size < period:
        return out
    alpha = 2.0 / (period + 1.0)
    # İlk EMA değeri, ilk `period` gözlemin basit ortalaması ile başlatılır.
    seed = arr[:period].mean()
    out[period - 1] = seed
    prev = seed
    for i in range(period, arr.size):
        prev = alpha * arr[i] + (1.0 - alpha) * prev
        out[i] = prev
    return out


def rsi(values: Sequence[float] | FloatArray, period: int = 14) -> FloatArray:
    """Göreceli Güç Endeksi (Relative Strength Index), Wilder yöntemi."""
    if period <= 0:
        raise ValueError("period pozitif olmalı.")
    arr = _as_array(values)
    out = np.full(arr.shape, np.nan, dtype=np.float64)
    if arr.size <= period:
        return out
    deltas = np.diff(arr)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()

    def _rsi_value(ag: float, al: float) -> float:
        if al == 0:
            return 100.0
        rs = ag / al
        return 100.0 - (100.0 / (1.0 + rs))

    out[period] = _rsi_value(avg_gain, avg_loss)
    for i in range(period + 1, arr.size):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        out[i] = _rsi_value(avg_gain, avg_loss)
    return out


@dataclass(frozen=True)
class MACDResult:
    """MACD çıktısı: MACD çizgisi, sinyal çizgisi ve histogram."""

    macd: FloatArray
    signal: FloatArray
    histogram: FloatArray


def macd(
    values: Sequence[float] | FloatArray,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> MACDResult:
    """Hareketli Ortalama Yakınsama Iraksama (MACD)."""
    if not (0 < fast_period < slow_period):
        raise ValueError("fast_period, slow_period'dan küçük ve pozitif olmalı.")
    if signal_period <= 0:
        raise ValueError("signal_period pozitif olmalı.")
    arr = _as_array(values)
    fast = ema(arr, fast_period)
    slow = ema(arr, slow_period)
    macd_line = fast - slow

    # Sinyal, MACD çizgisinin geçerli (NaN olmayan) kısmının EMA'sıdır.
    signal_line = np.full(arr.shape, np.nan, dtype=np.float64)
    valid = ~np.isnan(macd_line)
    if valid.sum() >= signal_period:
        start = int(np.argmax(valid))
        signal_valid = ema(macd_line[start:], signal_period)
        signal_line[start:] = signal_valid
    histogram = macd_line - signal_line
    return MACDResult(macd=macd_line, signal=signal_line, histogram=histogram)


def atr(
    high: Sequence[float] | FloatArray,
    low: Sequence[float] | FloatArray,
    close: Sequence[float] | FloatArray,
    period: int = 14,
) -> FloatArray:
    """Ortalama Gerçek Aralık (Average True Range), Wilder yöntemi."""
    if period <= 0:
        raise ValueError("period pozitif olmalı.")
    h = _as_array(high)
    low_arr = _as_array(low)
    c = _as_array(close)
    if not (h.size == low_arr.size == c.size):
        raise ValueError("high, low ve close aynı uzunlukta olmalı.")
    out = np.full(h.shape, np.nan, dtype=np.float64)
    if h.size <= period:
        return out

    prev_close = c[:-1]
    tr = np.empty(h.size, dtype=np.float64)
    tr[0] = h[0] - low_arr[0]
    tr[1:] = np.maximum.reduce(
        [
            h[1:] - low_arr[1:],
            np.abs(h[1:] - prev_close),
            np.abs(low_arr[1:] - prev_close),
        ]
    )

    first = tr[1 : period + 1].mean()
    out[period] = first
    prev = first
    for i in range(period + 1, h.size):
        prev = (prev * (period - 1) + tr[i]) / period
        out[i] = prev
    return out
