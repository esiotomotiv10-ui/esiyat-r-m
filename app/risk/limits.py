"""Risk limitleri ve pozisyon boyutlandırma.

Zorunlu kurallar (varsayılan değerler):
- İşlem başına azami risk %1
- Tek varlık azami ağırlığı %10
- Günlük azami zarar %3
- Portföy azami düşüşü %10
Kill switch etkinse hiçbir işlem onaylanmaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from app.core.config import Settings, get_settings
from app.core.kill_switch import KillSwitch, kill_switch


@dataclass(frozen=True)
class RiskLimits:
    """Risk limitleri (oran olarak, 0-1 arası)."""

    max_risk_per_trade: float = 0.01
    max_asset_weight: float = 0.10
    max_daily_loss: float = 0.03
    max_portfolio_drawdown: float = 0.10

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> RiskLimits:
        """Ayarlardan risk limitleri oluşturur."""
        s = settings or get_settings()
        return cls(
            max_risk_per_trade=s.max_risk_per_trade,
            max_asset_weight=s.max_asset_weight,
            max_daily_loss=s.max_daily_loss,
            max_portfolio_drawdown=s.max_portfolio_drawdown,
        )


@dataclass(frozen=True)
class RiskDecision:
    """Bir işlem talebine ilişkin risk kararı."""

    approved: bool
    reason: str
    max_quantity: float = 0.0


class RiskManager:
    """Risk limitlerini uygulayan yönetici."""

    def __init__(
        self,
        limits: RiskLimits | None = None,
        *,
        switch: KillSwitch | None = None,
    ) -> None:
        self.limits = limits or RiskLimits.from_settings()
        self._kill_switch = switch or kill_switch

    @staticmethod
    def _finite(value: float) -> bool:
        return isfinite(value)

    def position_size(
        self,
        *,
        equity: float,
        entry_price: float,
        stop_price: float,
    ) -> float:
        """İşlem başına azami risk kuralına göre adet hesaplar.

        Riske edilen tutar = equity * max_risk_per_trade. Adet, bu tutarın
        birim başına riske (giriş - stop farkı) bölünmesiyle bulunur.
        """
        if not self._finite(equity) or equity <= 0:
            raise ValueError("equity pozitif olmalı.")
        if not self._finite(entry_price) or entry_price <= 0:
            raise ValueError("entry_price pozitif olmalı.")
        if not self._finite(stop_price) or stop_price <= 0:
            raise ValueError("stop_price pozitif ve sonlu olmalı.")
        risk_per_unit = abs(entry_price - stop_price)
        if risk_per_unit <= 0:
            raise ValueError("stop_price, entry_price'tan farklı olmalı.")
        risk_budget = equity * self.limits.max_risk_per_trade
        return risk_budget / risk_per_unit

    def evaluate_trade(
        self,
        *,
        equity: float,
        entry_price: float,
        stop_price: float,
        quantity: float,
        current_asset_value: float = 0.0,
        daily_pnl: float = 0.0,
        drawdown: float = 0.0,
    ) -> RiskDecision:
        """Bir işlem talebini tüm risk limitlerine karşı değerlendirir."""
        if self._kill_switch.is_engaged:
            return RiskDecision(False, "Kill switch etkin — işlem reddedildi.")

        if not all(
            self._finite(value)
            for value in (
                equity,
                entry_price,
                stop_price,
                quantity,
                current_asset_value,
                daily_pnl,
                drawdown,
            )
        ):
            return RiskDecision(False, "Risk girdileri sonlu sayılar olmalı.")
        if equity <= 0:
            return RiskDecision(False, "Özkaynak (equity) pozitif olmalı.")
        if entry_price <= 0 or stop_price <= 0:
            return RiskDecision(False, "Fiyatlar pozitif olmalı.")
        if quantity <= 0:
            return RiskDecision(False, "Miktar pozitif olmalı.")
        if current_asset_value < 0:
            return RiskDecision(False, "Mevcut varlık değeri negatif olamaz.")
        if drawdown < 0:
            return RiskDecision(False, "Drawdown negatif olamaz.")

        # Günlük azami zarar kontrolü (daily_pnl negatif ise zarar).
        if daily_pnl < 0 and abs(daily_pnl) >= self.limits.max_daily_loss * equity:
            return RiskDecision(
                False,
                f"Günlük azami zarar limiti aşıldı (%{self.limits.max_daily_loss * 100:.0f}).",
            )

        # Portföy azami düşüşü kontrolü.
        if drawdown >= self.limits.max_portfolio_drawdown:
            pct = self.limits.max_portfolio_drawdown * 100
            return RiskDecision(
                False,
                f"Portföy azami düşüş limiti aşıldı (%{pct:.0f}).",
            )

        # İşlem başına azami risk kontrolü.
        risk_per_unit = abs(entry_price - stop_price)
        if risk_per_unit <= 0:
            return RiskDecision(False, "Geçersiz stop seviyesi.")
        trade_risk = risk_per_unit * quantity
        if not isfinite(trade_risk):
            return RiskDecision(False, "İşlem riski aşırı büyük.")
        max_trade_risk = self.limits.max_risk_per_trade * equity
        if trade_risk > max_trade_risk:
            allowed = self.position_size(
                equity=equity, entry_price=entry_price, stop_price=stop_price
            )
            return RiskDecision(
                False,
                f"İşlem başına azami risk aşıldı (%{self.limits.max_risk_per_trade * 100:.0f}).",
                max_quantity=allowed,
            )

        # Tek varlık azami ağırlığı kontrolü.
        prospective_value = current_asset_value + entry_price * quantity
        if not isfinite(prospective_value):
            return RiskDecision(False, "Pozisyon değeri aşırı büyük.")
        max_asset_value = self.limits.max_asset_weight * equity
        if prospective_value > max_asset_value:
            headroom = max(max_asset_value - current_asset_value, 0.0)
            allowed = headroom / entry_price if entry_price > 0 else 0.0
            return RiskDecision(
                False,
                f"Tek varlık azami ağırlığı aşıldı (%{self.limits.max_asset_weight * 100:.0f}).",
                max_quantity=allowed,
            )

        return RiskDecision(True, "İşlem risk limitleri içinde.", max_quantity=quantity)
