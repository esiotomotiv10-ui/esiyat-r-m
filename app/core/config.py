"""Uygulama yapılandırması.

Güvenlik kuralları kod seviyesinde zorlanır:
- Paper trading varsayılan ve zorunludur (``TRADING_MODE`` yalnızca ``paper``).
- Gerçek emir gönderimi kapalıdır (``LIVE_TRADING_DISABLED`` daima ``True``).
Ortam değişkeni bu kuralları gevşetmeye çalışırsa değer güvenli tarafa çekilir.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TradingMode(StrEnum):
    """Desteklenen işlem modları. Şimdilik yalnızca paper."""

    PAPER = "paper"


class Settings(BaseSettings):
    """Ortam değişkenlerinden yüklenen uygulama ayarları."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "esiyat-robot"
    environment: str = "development"
    log_level: str = "INFO"

    # --- Güvenlik / emir modu ---
    trading_mode: TradingMode = TradingMode.PAPER
    live_trading_disabled: bool = True
    kill_switch: bool = False
    enable_kill_switch_endpoint: bool = False

    # --- Risk parametreleri (oran, 0-1 arası) ---
    max_risk_per_trade: float = Field(default=0.01, gt=0, le=1)
    max_asset_weight: float = Field(default=0.10, gt=0, le=1)
    max_daily_loss: float = Field(default=0.03, gt=0, le=1)
    max_portfolio_drawdown: float = Field(default=0.10, gt=0, le=1)

    @field_validator("trading_mode", mode="before")
    @classmethod
    def _force_paper_mode(cls, value: object) -> str:
        """Paper dışı her mod güvenli tarafa (paper) çekilir."""
        if isinstance(value, str) and value.lower() != TradingMode.PAPER.value:
            return TradingMode.PAPER.value
        if isinstance(value, TradingMode):
            return value.value
        return TradingMode.PAPER.value

    @model_validator(mode="after")
    def _enforce_live_trading_disabled(self) -> Settings:
        """Gerçek emir gönderimi hiçbir koşulda açılamaz."""
        object.__setattr__(self, "live_trading_disabled", True)
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Önbelleğe alınmış tekil ayar örneğini döndürür."""
    return Settings()
