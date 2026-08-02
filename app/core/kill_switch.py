"""Kill switch — acil durum durdurma mekanizması.

Etkin olduğunda hiçbir emir (paper dahil) işlenmez. Süreç içi (in-memory)
bayrak ile ortam değişkeni birleştirilir; ikisinden biri aktifse durdurulur.
"""

from __future__ import annotations

import threading

from app.core.config import get_settings


class KillSwitch:
    """İş parçacığı güvenli acil durdurma bayrağı."""

    def __init__(self, *, initial: bool = False) -> None:
        self._lock = threading.Lock()
        self._engaged = initial

    def engage(self, reason: str | None = None) -> None:
        """Kill switch'i etkinleştirir (durdurur)."""
        with self._lock:
            self._engaged = True
        self._reason = reason

    def reset(self) -> None:
        """Süreç içi bayrağı sıfırlar. Ortam değişkeni hâlâ baskındır."""
        with self._lock:
            self._engaged = False
        self._reason = None

    @property
    def is_engaged(self) -> bool:
        """Ortam değişkeni veya süreç içi bayraktan biri aktifse True."""
        with self._lock:
            local = self._engaged
        return local or get_settings().kill_switch


# Uygulama genelinde paylaşılan tekil örnek.
kill_switch = KillSwitch()
