"""Mum serisi deposu (repository).

Yüklenmiş ``BarSeries`` nesnelerini sembol ve zaman dilimine göre saklar ve
sorgular. Bu iskelet sürümde yalnızca bellek içi (in-memory) uygulama vardır;
kalıcı depolama ileride aynı arayüz uygulanarak eklenebilir.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.market_data.base import Bar
from app.market_data.models import BarSeries, Timeframe


class BarRepository(ABC):
    """Mum serisi deposu için soyut arayüz."""

    @abstractmethod
    def save(self, series: BarSeries) -> None:
        """Bir seriyi kaydeder (aynı sembol+zaman dilimi varsa üzerine yazar)."""

    @abstractmethod
    def get(self, symbol: str, timeframe: Timeframe) -> BarSeries | None:
        """Sembol ve zaman dilimine göre seriyi döndürür (yoksa ``None``)."""

    @abstractmethod
    def symbols(self) -> list[str]:
        """Depoda kayıtlı benzersiz sembolleri döndürür."""


class InMemoryBarRepository(BarRepository):
    """Bellek içi mum serisi deposu."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, Timeframe], BarSeries] = {}

    def save(self, series: BarSeries) -> None:
        self._store[(series.symbol, series.timeframe)] = series

    def get(self, symbol: str, timeframe: Timeframe) -> BarSeries | None:
        return self._store.get((symbol, timeframe))

    def symbols(self) -> list[str]:
        return sorted({key[0] for key in self._store})

    def get_range(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> BarSeries | None:
        """Belirli tarih aralığındaki mumları içeren alt seriyi döndürür.

        Aralıkta hiç mum kalmazsa ``None`` döner.
        """
        series = self.get(symbol, timeframe)
        if series is None:
            return None
        selected: list[Bar] = [
            bar
            for bar in series
            if (start is None or bar.timestamp >= start) and (end is None or bar.timestamp <= end)
        ]
        if not selected:
            return None
        return BarSeries.from_bars(symbol=symbol, timeframe=timeframe, bars=selected)
