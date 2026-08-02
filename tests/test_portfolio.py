"""Portföy modeli testleri."""

from __future__ import annotations

import math

import pytest

from app.portfolio import Portfolio


def test_buy_and_equity() -> None:
    pf = Portfolio(cash=10_000)
    pf.apply_fill("AAPL", 10, 100)
    assert pf.cash == 9_000
    assert pf.positions["AAPL"].quantity == 10
    assert pf.equity({"AAPL": 110}) == 9_000 + 10 * 110


def test_sell_realizes_pnl() -> None:
    pf = Portfolio(cash=10_000)
    pf.apply_fill("AAPL", 10, 100)
    pf.apply_fill("AAPL", -10, 120)
    assert pf.realized_pnl == (120 - 100) * 10
    assert "AAPL" not in pf.positions


def test_partial_sell_keeps_remaining_position_and_average_cost() -> None:
    pf = Portfolio(cash=10_000)
    pf.apply_fill("AAPL", 10, 100)
    pf.apply_fill("AAPL", -4, 120)
    assert pf.positions["AAPL"].quantity == 6
    assert pf.positions["AAPL"].avg_price == 100
    assert pf.realized_pnl == 80
    assert pf.cash == 9_480


def test_insufficient_cash_raises() -> None:
    pf = Portfolio(cash=500)
    with pytest.raises(ValueError):
        pf.apply_fill("AAPL", 10, 100)


@pytest.mark.parametrize(
    ("quantity", "price"),
    [(0.0, 100.0), (math.nan, 100.0), (1.0, 0.0), (1.0, math.inf), (1e308, 1e308)],
)
def test_apply_fill_rejects_invalid_numbers(quantity: float, price: float) -> None:
    pf = Portfolio(cash=10_000)
    with pytest.raises(ValueError):
        pf.apply_fill("AAPL", quantity, price)


def test_equity_rejects_invalid_market_price() -> None:
    pf = Portfolio(cash=10_000)
    pf.apply_fill("AAPL", 1, 100)
    with pytest.raises(ValueError):
        pf.equity({"AAPL": math.nan})


def test_no_short_selling() -> None:
    pf = Portfolio(cash=10_000)
    pf.apply_fill("AAPL", 5, 100)
    with pytest.raises(ValueError):
        pf.apply_fill("AAPL", -10, 100)


def test_drawdown_tracking() -> None:
    pf = Portfolio(cash=10_000)
    assert pf.drawdown({}) == 0.0
    pf.apply_fill("AAPL", 10, 100)  # equity hâlâ 10k
    # Fiyat düşerse düşüş oluşur.
    dd = pf.drawdown({"AAPL": 50})  # equity = 9000+500 = 9500 vs peak 10000
    assert dd == pytest.approx(0.05)
