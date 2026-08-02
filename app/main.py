"""FastAPI uygulama giriş noktası.

Uygulama başlarken güvenlik kuralları doğrulanır: paper trading zorunlu ve
gerçek emir gönderimi kapalı olmalıdır. Bu koşullar sağlanmazsa uygulama
başlatılmaz.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api import router
from app.core.config import TradingMode, get_settings


def _verify_safety_invariants() -> None:
    """Zorunlu güvenlik kurallarını doğrular; ihlalde hata yükseltir."""
    settings = get_settings()
    if settings.trading_mode is not TradingMode.PAPER:
        raise RuntimeError("Paper trading zorunludur; başka mod desteklenmez.")
    if not settings.live_trading_disabled:
        raise RuntimeError("Gerçek emir gönderimi kapalı olmalıdır.")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Uygulama yaşam döngüsü — başlangıçta güvenlik doğrulaması yapılır."""
    _verify_safety_invariants()
    yield


def create_app() -> FastAPI:
    """FastAPI uygulamasını oluşturur ve yapılandırır."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Güvenli yatırım robotu backend iskeleti (paper trading).",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


app = create_app()
