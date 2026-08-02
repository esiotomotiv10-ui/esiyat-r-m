"""Yapılandırma güvenlik kuralları testleri."""

from __future__ import annotations

from app.core.config import Settings, TradingMode


def test_default_is_paper_and_live_disabled() -> None:
    settings = Settings()
    assert settings.trading_mode is TradingMode.PAPER
    assert settings.live_trading_disabled is True


def test_non_paper_mode_forced_to_paper() -> None:
    settings = Settings(trading_mode="live")  # type: ignore[arg-type]
    assert settings.trading_mode is TradingMode.PAPER


def test_live_trading_cannot_be_enabled() -> None:
    settings = Settings(live_trading_disabled=False)
    assert settings.live_trading_disabled is True


def test_default_risk_limits() -> None:
    settings = Settings()
    assert settings.max_risk_per_trade == 0.01
    assert settings.max_asset_weight == 0.10
    assert settings.max_daily_loss == 0.03
    assert settings.max_portfolio_drawdown == 0.10
