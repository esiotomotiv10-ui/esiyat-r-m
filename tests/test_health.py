"""API uç noktaları testleri."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.kill_switch import kill_switch
from app.main import create_app


def _client() -> TestClient:
    get_settings.cache_clear()
    return TestClient(create_app())


def test_health_endpoint() -> None:
    with _client() as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["app_name"]
    assert body["version"]


def test_safety_status_enforces_paper_and_live_disabled() -> None:
    with _client() as client:
        resp = client.get("/safety")
    assert resp.status_code == 200
    body = resp.json()
    assert body["trading_mode"] == "paper"
    assert body["live_trading_disabled"] is True
    assert body["max_risk_per_trade"] == 0.01
    assert body["max_asset_weight"] == 0.10
    assert body["max_daily_loss"] == 0.03
    assert body["max_portfolio_drawdown"] == 0.10


def test_kill_switch_endpoint_disabled_by_default() -> None:
    kill_switch.reset()
    with _client() as client:
        resp = client.post("/safety/kill-switch", json={"engaged": True, "reason": "test"})
    assert resp.status_code == 404
    assert kill_switch.is_engaged is False


def test_kill_switch_toggle_when_explicitly_enabled_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENABLE_KILL_SWITCH_ENDPOINT", "true")
    monkeypatch.setenv("ENVIRONMENT", "development")
    kill_switch.reset()
    with _client() as client:
        engage = client.post("/safety/kill-switch", json={"engaged": True, "reason": "test"})
        assert engage.status_code == 200
        assert engage.json()["kill_switch_engaged"] is True

        reset = client.post("/safety/kill-switch", json={"engaged": False})
        assert reset.status_code == 200
        assert reset.json()["kill_switch_engaged"] is False
    kill_switch.reset()
    get_settings.cache_clear()


def _bar(day: int, open_price: float, close_price: float) -> dict[str, object]:
    return {
        "timestamp": f"2024-01-{day:02d}T00:00:00",
        "open": open_price,
        "high": max(open_price, close_price) + 1,
        "low": min(open_price, close_price) - 1,
        "close": close_price,
        "volume": 1000,
    }


def _backtest_payload() -> dict[str, object]:
    return {
        "symbol": "aapl",
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


def test_backtest_endpoint_runs_paper_only_backtest() -> None:
    with _client() as client:
        resp = client.post("/backtests", json=_backtest_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "AAPL"
    assert body["initial_cash"] == 100_000
    assert body["ending_cash"] >= 0
    assert body["final_equity"] > 0
    assert "total_return" in body
    assert "max_drawdown" in body
    assert "winning_trades" in body
    assert "losing_trades" in body
    assert "win_rate" in body
    assert len(body["equity_curve"]) == 10
    assert body["trade_count"] == len(body["trades"])


def test_backtest_endpoint_fills_signal_on_next_bar_open() -> None:
    payload = _backtest_payload()
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 200
    trades = resp.json()["trades"]
    assert trades
    assert trades[0]["timestamp"] == "2024-01-08T00:00:00Z"
    assert trades[0]["price"] == 21


def test_backtest_endpoint_respects_kill_switch() -> None:
    kill_switch.engage("test")
    try:
        with _client() as client:
            resp = client.post("/backtests", json=_backtest_payload())
    finally:
        kill_switch.reset()
    assert resp.status_code == 200
    body = resp.json()
    assert body["trade_count"] == 0
    assert body["trades"] == []


def test_backtest_endpoint_rejects_unsorted_bars() -> None:
    payload = _backtest_payload()
    bars = payload["bars"]
    assert isinstance(bars, list)
    bars[0], bars[1] = bars[1], bars[0]
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422


def test_backtest_endpoint_rejects_invalid_config() -> None:
    payload = _backtest_payload()
    config = payload["config"]
    assert isinstance(config, dict)
    config["commission_rate"] = -0.01
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422


def test_backtest_endpoint_rejects_unknown_strategy() -> None:
    payload = _backtest_payload()
    payload["strategy"] = {"name": "live_broker"}
    with _client() as client:
        resp = client.post("/backtests", json=payload)
    assert resp.status_code == 422
