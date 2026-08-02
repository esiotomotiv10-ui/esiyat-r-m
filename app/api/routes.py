"""API yönlendiricileri.

Sağlık kontrolü, güvenlik durumu ve kill switch yönetimi uç noktaları.
Herhangi bir gerçek emir uç noktası bilinçli olarak eklenmemiştir.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.kill_switch import kill_switch

router = APIRouter()
management_router = APIRouter()


class HealthResponse(BaseModel):
    """/health yanıt modeli."""

    status: str
    app_name: str
    environment: str
    version: str


class SafetyStatus(BaseModel):
    """Güvenlik ve risk yapılandırması özeti."""

    trading_mode: str
    live_trading_disabled: bool
    kill_switch_engaged: bool
    max_risk_per_trade: float
    max_asset_weight: float
    max_daily_loss: float
    max_portfolio_drawdown: float


class KillSwitchRequest(BaseModel):
    """Kill switch değiştirme isteği."""

    engaged: bool
    reason: str | None = None


class KillSwitchResponse(BaseModel):
    """Kill switch durum yanıtı."""

    kill_switch_engaged: bool


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Basit sağlık kontrolü."""
    from app import __version__

    settings = get_settings()
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        environment=settings.environment,
        version=__version__,
    )


@router.get("/safety", response_model=SafetyStatus, tags=["safety"])
def safety_status() -> SafetyStatus:
    """Zorunlu güvenlik kurallarını ve risk limitlerini gösterir."""
    settings = get_settings()
    return SafetyStatus(
        trading_mode=settings.trading_mode.value,
        live_trading_disabled=settings.live_trading_disabled,
        kill_switch_engaged=kill_switch.is_engaged,
        max_risk_per_trade=settings.max_risk_per_trade,
        max_asset_weight=settings.max_asset_weight,
        max_daily_loss=settings.max_daily_loss,
        max_portfolio_drawdown=settings.max_portfolio_drawdown,
    )


@management_router.post("/safety/kill-switch", response_model=KillSwitchResponse, tags=["safety"])
def set_kill_switch(request: KillSwitchRequest) -> KillSwitchResponse:
    """Kill switch'i etkinleştirir veya süreç içi bayrağı sıfırlar."""
    if request.engaged:
        kill_switch.engage(request.reason)
    else:
        kill_switch.reset()
    return KillSwitchResponse(kill_switch_engaged=kill_switch.is_engaged)
