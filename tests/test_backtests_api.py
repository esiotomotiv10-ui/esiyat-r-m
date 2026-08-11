"""``POST /backtests`` API katmanı doğrulama ve güvenlik testleri.

``tests/test_health.py`` içindeki temel akış testlerini tekrar etmez;
yalnızca istek doğrulama, DoS-koruması ve güvenlik davranışlarına
odaklanır.
"""

from __future__ import annotations

import json
import math

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.backtests import MAX_BARS
from app.core.config import get_settings
from app.core.kill_switch import kill_switch
from app.main import create_app


def _client() -> TestClient:
    get_settings.cache_clear()
    return TestClient(create_app())


def _bar(day: int, open_price: float, close_price: float) -> dict[str, object]:
    return {
        "timestamp": f"2024-01-{day:02d}T00:00:00",
        "open": open_price,
        "high": max(open_price, close_price) + 1,
        "low": min(open_price, close_price) - 1,
        "close": close_price,
        "volume": 1000,
    }


def _post_raw(client: TestClient, payload: dict[str, object]) -> httpx.Response:
    """``httpx`` refuses to encode NaN/Infinity via ``json=`` (allow_nan=False).

    Encode the body ourselves (stdlib ``json.dumps`` defaults to
    ``allow_nan=True``, matching how a real malicious client could send
    non-compliant-but-parseable JSON) and post it as raw bytes.
    """
    body = json.dumps(payload).encode("utf-8")
    return client.post("/backtests", content=body, headers={"content-type": "application/json"})


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "symbol": "AAPL",
        "timeframe": "1d",
        "bars": [
            _bar(1, 20, 20),
            _bar(2, 18, 18),
            _bar(3, 16, 16),
            _bar(4, 14, 14),
            _bar(5, 12, 12),
            _bar(6, 14, 14),
            _bar(7, 30, 17),
            _bar(8, 21, 21),
            _bar(9, 26, 26),
            _bar(10, 32, 32),
        ],
        "strategy": {"name": "sma_crossover", "short_period": 2, "long_period": 4},
        "config": {
            "initial_cash": 100_000,
            "stop_loss_pct": 0.15,
            "commission_rate": 0,
            "slippage_rate": 0,
            "warmup": 0,
        },
    }
    payload.update(overrides)
    return payload


# --- Broker/veri kaynağı/emir modu seçilemez -----------------------------


@pytest.mark.parametrize(
    "extra_field",
    [
        {"broker": "real_broker"},
        {"data_source": "live_feed"},
        {"trading_mode": "live"},
        {"live": True},
        {"order_mode": "market_live"},
    ],
)
def test_unknown_or_broker_related_fields_are_rejected(extra_field: dict[str, object]) -> None:
    payload = _payload(**extra_field)
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422


def test_extra_unknown_field_at_bar_level_is_rejected() -> None:
    payload = _payload()
    bars = payload["bars"]
    assert isinstance(bars, list)
    bars[0] = {**bars[0], "broker_override": "real"}
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422


def test_extra_unknown_field_at_strategy_level_is_rejected() -> None:
    strategy = {"name": "sma_crossover", "short_period": 2, "long_period": 4, "live": True}
    payload = _payload(strategy=strategy)
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422


def test_extra_unknown_field_at_config_level_is_rejected() -> None:
    payload = _payload()
    config = payload["config"]
    assert isinstance(config, dict)
    config["real_broker_api_key"] = "secret"
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422


# --- Yalnızca sma_crossover ------------------------------------------------


def test_only_sma_crossover_strategy_name_is_accepted() -> None:
    payload = _payload(strategy={"name": "ema_crossover"})
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422


def test_invalid_strategy_config_short_period_not_less_than_long_period() -> None:
    payload = _payload(strategy={"name": "sma_crossover", "short_period": 10, "long_period": 10})
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422


# --- Symbol doğrulaması -----------------------------------------------------


@pytest.mark.parametrize("symbol", ["", "   ", "\t\n"])
def test_empty_or_whitespace_symbol_is_rejected(symbol: str) -> None:
    payload = _payload(symbol=symbol)
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422


def test_symbol_with_invalid_characters_is_rejected() -> None:
    payload = _payload(symbol="AAPL;DROP TABLE")
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422


def test_symbol_is_normalized_to_uppercase() -> None:
    payload = _payload(symbol="aapl")
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 200
    assert resp.json()["symbol"] == "AAPL"


# --- Timestamp / timezone doğrulaması ---------------------------------------


def test_duplicate_timestamps_are_rejected() -> None:
    payload = _payload()
    bars = payload["bars"]
    assert isinstance(bars, list)
    bars[1] = {**bars[1], "timestamp": bars[0]["timestamp"]}
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422


def test_out_of_order_timestamps_are_rejected() -> None:
    payload = _payload()
    bars = payload["bars"]
    assert isinstance(bars, list)
    bars[0], bars[2] = bars[2], bars[0]
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422


def test_mixed_naive_and_aware_timestamps_do_not_crash_and_are_handled() -> None:
    """Naive/aware timestamp karışımı yakalanmamış bir ``TypeError``
    yerine 200 (normalize edilmiş) veya 422 (doğrulama hatası) döndürmeli;
    hiçbir koşulda sunucu hatası (500) sızdırmamalı."""
    payload = _payload()
    bars = payload["bars"]
    assert isinstance(bars, list)
    bars[0] = {**bars[0], "timestamp": "2024-01-01T00:00:00+00:00"}
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code in (200, 422)


def test_naive_timestamp_is_accepted_and_treated_as_utc() -> None:
    payload = _payload()
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 200


# --- OHLC tutarlılığı --------------------------------------------------------


def test_malformed_ohlc_high_below_close_is_rejected() -> None:
    payload = _payload()
    bars = payload["bars"]
    assert isinstance(bars, list)
    bars[0] = {**bars[0], "high": 5, "low": 1, "open": 4, "close": 20}
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422


def test_malformed_ohlc_low_above_open_is_rejected() -> None:
    payload = _payload()
    bars = payload["bars"]
    assert isinstance(bars, list)
    bars[0] = {**bars[0], "open": 10, "high": 20, "low": 15, "close": 12}
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422


def test_negative_or_zero_price_is_rejected() -> None:
    payload = _payload()
    bars = payload["bars"]
    assert isinstance(bars, list)
    bars[0] = {**bars[0], "open": 0}
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422


def test_negative_volume_is_rejected() -> None:
    payload = _payload()
    bars = payload["bars"]
    assert isinstance(bars, list)
    bars[0] = {**bars[0], "volume": -1}
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422


# --- NaN / Infinity ----------------------------------------------------------


@pytest.mark.parametrize("field", ["open", "high", "low", "close", "volume"])
@pytest.mark.parametrize("bad_value", [math.nan, math.inf, -math.inf])
def test_nan_and_inf_bar_fields_are_rejected(field: str, bad_value: float) -> None:
    payload = _payload()
    bars = payload["bars"]
    assert isinstance(bars, list)
    bars[0] = {**bars[0], field: bad_value}
    with _client() as client:
        resp = _post_raw(client, payload)
    assert resp.status_code == 422


@pytest.mark.parametrize("bad_value", [math.nan, math.inf, -math.inf])
def test_nan_and_inf_config_fields_are_rejected(bad_value: float) -> None:
    payload = _payload()
    config = payload["config"]
    assert isinstance(config, dict)
    config["commission_rate"] = bad_value
    with _client() as client:
        resp = _post_raw(client, payload)
    assert resp.status_code == 422


# --- Aşırı büyük istekler (DoS koruması) ------------------------------------


def test_bar_count_over_the_maximum_is_rejected() -> None:
    payload = _payload(
        bars=[_bar(i, 20, 20) for i in range(1, MAX_BARS + 2)],
    )
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422


def test_empty_bar_list_is_rejected() -> None:
    payload = _payload(bars=[])
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422


@pytest.mark.parametrize("field", ["short_period", "long_period"])
def test_huge_period_values_are_rejected(field: str) -> None:
    payload = _payload(strategy={"name": "sma_crossover", field: 10**9})
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422


def test_huge_warmup_value_is_rejected() -> None:
    payload = _payload()
    config = payload["config"]
    assert isinstance(config, dict)
    config["warmup"] = 10**9
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422


# --- Komisyon / slippage -----------------------------------------------------


def test_commission_plus_slippage_at_or_above_one_is_rejected() -> None:
    payload = _payload()
    config = payload["config"]
    assert isinstance(config, dict)
    config["commission_rate"] = 0.5
    config["slippage_rate"] = 0.5
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422


def test_negative_commission_rate_is_rejected() -> None:
    payload = _payload()
    config = payload["config"]
    assert isinstance(config, dict)
    config["commission_rate"] = -0.01
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422


def test_negative_slippage_rate_is_rejected() -> None:
    payload = _payload()
    config = payload["config"]
    assert isinstance(config, dict)
    config["slippage_rate"] = -0.01
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422


def test_commission_and_slippage_affect_response_deterministically() -> None:
    payload = _payload()
    config = payload["config"]
    assert isinstance(config, dict)
    config["commission_rate"] = 0.01
    config["slippage_rate"] = 0.01
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 200
    trades = resp.json()["trades"]
    assert trades
    # Alış fiyatı, referans açılış fiyatının üzerinde olmalı (komisyon +
    # slippage alışta fiyatı yukarı çeker).
    buy = next(t for t in trades if t["side"] == "buy")
    assert buy["price"] > 21


# --- Invalid timeframe --------------------------------------------------------


def test_invalid_timeframe_is_rejected() -> None:
    payload = _payload(timeframe="3d")
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422


# --- Kill switch --------------------------------------------------------------


def test_kill_switch_prevents_any_trade_via_api() -> None:
    kill_switch.engage("api-test")
    try:
        with _client() as client:
            resp = client.post("/backtests", json=_payload())
    finally:
        kill_switch.reset()
    assert resp.status_code == 200
    body = resp.json()
    assert body["trade_count"] == 0
    assert body["trades"] == []


def test_kill_switch_state_matches_global_app_state() -> None:
    """Backtest, ``app.core.kill_switch.kill_switch`` tekil örneğini
    kullanmalı; ayrı/izole bir kill switch durumu olmamalı."""
    kill_switch.engage("global-state-test")
    try:
        with _client() as client:
            safety = client.get("/safety").json()
            backtest_resp = client.post("/backtests", json=_payload())
        assert safety["kill_switch_engaged"] is True
        assert backtest_resp.json()["trade_count"] == 0
    finally:
        kill_switch.reset()


# --- Son bar sinyali fill edilmiyor -------------------------------------------


def test_last_bar_signal_is_never_filled_via_api() -> None:
    # Son iki mumda golden cross oluşacak şekilde kurgulanmış seri; sinyal
    # son barda üretilse bile hiçbir işlem gerçekleşmemeli (fill edilecek
    # bir sonraki bar yok).
    bars = [_bar(i, 12 + i, 12 + i) for i in range(1, 5)] + [_bar(5, 30, 40)]
    payload = _payload(
        bars=bars,
        strategy={"name": "sma_crossover", "short_period": 2, "long_period": 3},
    )
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    if body["trades"]:
        assert body["trades"][-1]["timestamp"] != bars[-1]["timestamp"]


# --- Deterministik yanıt -------------------------------------------------------


def test_backtest_response_is_deterministic_across_calls() -> None:
    payload = _payload()
    with _client() as client:
        first = client.post("/backtests", json=payload).json()
        second = client.post("/backtests", json=payload).json()
    assert first == second


# --- Tüm sayısal alanlar finite -----------------------------------------------


def test_response_numeric_fields_are_all_finite() -> None:
    payload = _payload()
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    numeric_fields = (
        "initial_cash",
        "ending_cash",
        "final_equity",
        "total_return",
        "max_drawdown",
        "win_rate",
    )
    for field in numeric_fields:
        assert math.isfinite(body[field]), field
    for point in body["equity_curve"]:
        assert math.isfinite(point["equity"])
    for trade in body["trades"]:
        for key in ("quantity", "price", "realized_pnl", "notional"):
            assert math.isfinite(trade[key]), key


# --- Hata mesajları iç detay sızdırmıyor ---------------------------------------


def test_validation_error_does_not_leak_internal_details() -> None:
    payload = _payload()
    bars = payload["bars"]
    assert isinstance(bars, list)
    bars[0], bars[1] = bars[1], bars[0]
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422
    text = resp.text.lower()
    for leaky_token in ("traceback", "site-packages", '.py"', "line ", "raise "):
        assert leaky_token not in text
