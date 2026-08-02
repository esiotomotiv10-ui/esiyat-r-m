"""Piyasa sınıfları: BIST, ABD hisseleri ve altın.

Her sınıf sembol normalizasyonu ve para birimi gibi piyasaya özgü kuralları
tanımlar. Canlı veri erişimi henüz bağlı değildir; ``get_quote`` ve
``get_history`` bilinçli olarak ``NotImplementedError`` yükseltir.
"""

from __future__ import annotations

from app.market_data.base import AssetClass, Bar, MarketDataProvider, Quote


class _StubMarket(MarketDataProvider):
    """Canlı kaynak bağlı olmayan sağlayıcılar için ortak stub davranışı."""

    def get_quote(self, symbol: str) -> Quote:
        raise NotImplementedError("Canlı piyasa verisi bu iskelet sürümde bağlı değildir.")

    def get_history(self, symbol: str, limit: int = 100) -> list[Bar]:
        raise NotImplementedError("Geçmiş piyasa verisi bu iskelet sürümde bağlı değildir.")


class BISTMarket(_StubMarket):
    """Borsa İstanbul hisse senetleri piyasası."""

    asset_class = AssetClass.BIST_EQUITY
    currency = "TRY"

    def normalize_symbol(self, symbol: str) -> str:
        """BIST sembolünü ``.IS`` uzantısıyla normalize eder (örn. THYAO.IS)."""
        base = symbol.strip().upper().removesuffix(".IS")
        if not base:
            raise ValueError("Sembol boş olamaz.")
        return f"{base}.IS"


class USEquityMarket(_StubMarket):
    """ABD hisse senetleri piyasası."""

    asset_class = AssetClass.US_EQUITY
    currency = "USD"

    def normalize_symbol(self, symbol: str) -> str:
        """ABD sembolünü büyük harfe çevirerek normalize eder (örn. AAPL)."""
        base = symbol.strip().upper()
        if not base:
            raise ValueError("Sembol boş olamaz.")
        return base


class GoldMarket(_StubMarket):
    """Altın (emtia) piyasası."""

    asset_class = AssetClass.COMMODITY_GOLD
    currency = "USD"

    # Yaygın altın sembolleri için takma ad eşlemesi.
    _ALIASES = {
        "GOLD": "XAUUSD",
        "ALTIN": "XAUUSD",
        "GRAMALTIN": "XAUTRY",
        "GRAM": "XAUTRY",
    }

    def normalize_symbol(self, symbol: str) -> str:
        """Altın sembolünü standart forma (örn. XAUUSD) normalize eder."""
        base = symbol.strip().upper().replace("/", "")
        if not base:
            raise ValueError("Sembol boş olamaz.")
        return self._ALIASES.get(base, base)
