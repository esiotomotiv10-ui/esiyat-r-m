"""Emir yürütme ve paper broker testleri."""

from __future__ import annotations

import pytest

from app.brokers import Order, OrderSide, PaperBroker
from app.core.kill_switch import KillSwitch
from app.execution import ExecutionEngine
from app.portfolio import Portfolio
from app.risk.limits import RiskLimits, RiskManager


def _engine(switch: KillSwitch | None = None) -> ExecutionEngine:
    sw = switch or KillSwitch()
    return ExecutionEngine(
        portfolio=Portfolio(cash=100_000),
        risk_manager=RiskManager(RiskLimits(), switch=sw),
        broker=PaperBroker(switch=sw),
        switch=sw,
    )


def test_paper_broker_is_paper() -> None:
    assert PaperBroker().is_paper is True


def test_execution_buy_updates_portfolio() -> None:
    engine = _engine()
    order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=50)
    report = engine.execute(order, reference_price=100, stop_price=95)
    assert report.executed
    assert report.order_result is not None
    assert report.order_result.is_paper is True
    assert engine.portfolio.positions["AAPL"].quantity == 50
    assert engine.portfolio.cash == 100_000 - 50 * 100


def test_execution_blocked_by_kill_switch() -> None:
    switch = KillSwitch(initial=True)
    engine = _engine(switch)
    order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10)
    report = engine.execute(order, reference_price=100, stop_price=95)
    assert not report.executed
    assert "Kill switch" in report.reason


def test_execution_rejects_oversized_risk() -> None:
    engine = _engine()
    order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10_000)
    report = engine.execute(order, reference_price=100, stop_price=95)
    assert not report.executed


def test_engine_rejects_non_paper_broker() -> None:
    class FakeLiveBroker(PaperBroker):
        is_paper = False

    with pytest.raises(RuntimeError):
        ExecutionEngine(portfolio=Portfolio(cash=1_000), broker=FakeLiveBroker())
