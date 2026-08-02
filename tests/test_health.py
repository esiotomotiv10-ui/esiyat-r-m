"""API uç noktaları testleri."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.kill_switch import kill_switch
from app.main import create_app


def _client() -> TestClient:
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


def test_kill_switch_toggle() -> None:
    kill_switch.reset()
    with _client() as client:
        engage = client.post("/safety/kill-switch", json={"engaged": True, "reason": "test"})
        assert engage.status_code == 200
        assert engage.json()["kill_switch_engaged"] is True

        reset = client.post("/safety/kill-switch", json={"engaged": False})
        assert reset.status_code == 200
        assert reset.json()["kill_switch_engaged"] is False
    kill_switch.reset()
