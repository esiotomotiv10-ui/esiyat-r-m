"""FastAPI uygulama giriş noktası.

Uygulama başlarken güvenlik kuralları doğrulanır: paper trading zorunlu ve
gerçek emir gönderimi kapalı olmalıdır. Bu koşullar sağlanmazsa uygulama
başlatılmaz.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from math import isfinite
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import __version__
from app.api import backtest_router, management_router, router
from app.core.config import TradingMode, get_settings


def _verify_safety_invariants() -> None:
    """Zorunlu güvenlik kurallarını doğrular; ihlalde hata yükseltir."""
    settings = get_settings()
    if settings.trading_mode is not TradingMode.PAPER:
        raise RuntimeError("Paper trading zorunludur; başka mod desteklenmez.")
    if not settings.live_trading_disabled:
        raise RuntimeError("Gerçek emir gönderimi kapalı olmalıdır.")


def _sanitize_for_json(value: Any) -> Any:
    """422 hata gövdesindeki reddedilmiş girdi değerlerini JSON-uyumlu hale getirir.

    Starlette'in varsayılan ``JSONResponse`` render'ı ``allow_nan=False``
    kullanır (RFC uyumlu JSON). Pydantic doğrulama hataları, reddedilen NaN/
    Infinity girdisini ``detail[].input`` alanında olduğu gibi geri yansıtır;
    bu değer sanitize edilmezse hata yanıtının kendisi serileştirme
    aşamasında yakalanmamış bir ``ValueError`` ile 500'e düşer (istemci
    girdisi kaynaklı bir 422 yerine).
    """
    if isinstance(value, float) and not isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {key: _sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_json(item) for item in value]
    return value


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
    app.include_router(backtest_router)
    if settings.enable_kill_switch_endpoint and settings.environment == "development":
        app.include_router(management_router)

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Doğrulama hatalarını, sanitize edilmiş içerikle 422 olarak döndürür."""
        errors = jsonable_encoder(exc.errors())
        return JSONResponse(
            status_code=422,
            content={"detail": _sanitize_for_json(errors)},
        )

    return app


app = create_app()
