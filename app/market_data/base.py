"""Piyasa veri sağlayıcı arayüzü ve temel veri modelleri.

Bu iskelet sürümde canlı veri kaynağı yoktur. Sağlayıcılar arayüz/stub
seviyesindedir; gerçek entegrasyon ileride bu arayüzü uygulayarak eklenir.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class AssetClass(StrEnum):
    """Desteklenen varlık sınıfları."""

    BIST_EQUITY = "bist_equity"
    US_EQUITY = "us_equity"
    COMMODITY_GOLD = "commodity_gold"


@dataclass(frozen=True)
class Quote:
    """Anlık fiyat kotasyonu."""

    symbol: str
    price: float
    currency: str
    timestamp: datetime


@dataclass(frozen=True)
class Bar:
    """OHLCV mum verisi."""

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketDataProvider(ABC):
    """Piyasa veri sağlayıcıları için soyut arayüz (stub)."""

    asset_class: AssetClass
    currency: str

    @abstractmethod
    def normalize_symbol(self, symbol: str) -> str:
        """Sembolü piyasaya özgü kurallara göre normalize eder."""

    @abstractmethod
    def get_quote(self, symbol: str) -> Quote:
        """Sembol için anlık kotasyon döndürür.

        İskelet sürümde canlı kaynak bağlı olmadığından
        ``NotImplementedError`` yükseltilir.
        """

    @abstractmethod
    def get_history(self, symbol: str, limit: int = 100) -> list[Bar]:
        """Sembol için geçmiş OHLCV verisi döndürür (stub)."""
