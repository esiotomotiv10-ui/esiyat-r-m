"""Portföy modeli testleri."""

from __future__ import annotations

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


def test_insufficient_cash_raises() -> None:
    pf = Portfolio(cash=500)
    with pytest.raises(ValueError):
        pf.apply_fill("AAPL", 10, 100)


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
