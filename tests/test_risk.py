"""Risk yönetimi testleri."""

from __future__ import annotations

import math

import pytest

from app.core.kill_switch import KillSwitch
from app.risk.limits import RiskLimits, RiskManager


def _manager(switch: KillSwitch | None = None) -> RiskManager:
    return RiskManager(RiskLimits(), switch=switch or KillSwitch())


def test_position_size_respects_risk_per_trade() -> None:
    mgr = _manager()
    # equity 100k, risk %1 => 1000 bütçe; birim risk 10 => 100 adet.
    qty = mgr.position_size(equity=100_000, entry_price=100, stop_price=90)
    assert qty == 100.0


@pytest.mark.parametrize(
    ("entry_price", "stop_price"),
    [
        (0.0, 90.0),
        (-1.0, 90.0),
        (100.0, 0.0),
        (100.0, 100.0),
        (math.nan, 90.0),
        (100.0, math.inf),
    ],
)
def test_position_size_rejects_invalid_prices(entry_price: float, stop_price: float) -> None:
    mgr = _manager()
    with pytest.raises(ValueError):
        mgr.position_size(equity=100_000, entry_price=entry_price, stop_price=stop_price)


def test_trade_within_limits_approved() -> None:
    mgr = _manager()
    decision = mgr.evaluate_trade(
        equity=100_000,
        entry_price=100,
        stop_price=95,
        quantity=100,  # risk = 5*100 = 500 <= 1000
    )
    assert decision.approved


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("equity", math.nan),
        ("entry_price", math.inf),
        ("stop_price", math.nan),
        ("quantity", math.inf),
        ("current_asset_value", math.nan),
        ("daily_pnl", math.inf),
        ("drawdown", math.nan),
    ],
)
def test_trade_rejects_non_finite_inputs(field: str, value: float) -> None:
    mgr = _manager()
    kwargs = {
        "equity": 100_000.0,
        "entry_price": 100.0,
        "stop_price": 95.0,
        "quantity": 1.0,
        "current_asset_value": 0.0,
        "daily_pnl": 0.0,
        "drawdown": 0.0,
    }
    kwargs[field] = value
    decision = mgr.evaluate_trade(**kwargs)
    assert not decision.approved
    assert "sonlu" in decision.reason


@pytest.mark.parametrize(
    ("entry_price", "stop_price", "quantity"),
    [(0.0, 95.0, 1.0), (100.0, 0.0, 1.0), (100.0, 95.0, 0.0), (100.0, 95.0, -1.0)],
)
def test_trade_rejects_invalid_price_or_quantity(
    entry_price: float, stop_price: float, quantity: float
) -> None:
    mgr = _manager()
    decision = mgr.evaluate_trade(
        equity=100_000,
        entry_price=entry_price,
        stop_price=stop_price,
        quantity=quantity,
    )
    assert not decision.approved


def test_trade_rejects_extremely_large_quantity() -> None:
    mgr = _manager()
    decision = mgr.evaluate_trade(
        equity=100_000,
        entry_price=1e308,
        stop_price=1.0,
        quantity=1e308,
    )
    assert not decision.approved


def test_trade_exceeds_risk_per_trade_rejected() -> None:
    mgr = _manager()
    decision = mgr.evaluate_trade(
        equity=100_000,
        entry_price=100,
        stop_price=95,
        quantity=1000,  # risk = 5*1000 = 5000 > 1000
    )
    assert not decision.approved
    assert decision.max_quantity == 200.0  # 1000 / 5


def test_asset_weight_limit_rejected() -> None:
    mgr = _manager()
    # equity 100k, azami ağırlık %10 => 10k. 200 adet * 100 = 20k > 10k.
    decision = mgr.evaluate_trade(
        equity=100_000,
        entry_price=100,
        stop_price=99.9,  # risk küçük, ağırlık limiti devreye girsin
        quantity=200,
    )
    assert not decision.approved
    assert "ağırlığı" in decision.reason


def test_daily_loss_limit_rejected() -> None:
    mgr = _manager()
    decision = mgr.evaluate_trade(
        equity=100_000,
        entry_price=100,
        stop_price=99,
        quantity=1,
        daily_pnl=-3_500,  # %3.5 zarar > %3 limit
    )
    assert not decision.approved
    assert "Günlük" in decision.reason


def test_drawdown_limit_rejected() -> None:
    mgr = _manager()
    decision = mgr.evaluate_trade(
        equity=100_000,
        entry_price=100,
        stop_price=99,
        quantity=1,
        drawdown=0.11,  # %11 > %10 limit
    )
    assert not decision.approved
    assert "düşüş" in decision.reason


def test_kill_switch_blocks_all_trades() -> None:
    switch = KillSwitch(initial=True)
    mgr = _manager(switch)
    decision = mgr.evaluate_trade(equity=100_000, entry_price=100, stop_price=99, quantity=1)
    assert not decision.approved
    assert "Kill switch" in decision.reason
