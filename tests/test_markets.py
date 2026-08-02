"""Piyasa sınıfları testleri."""

from __future__ import annotations

import pytest

from app.market_data import BISTMarket, GoldMarket, USEquityMarket


def test_bist_symbol_normalization() -> None:
    market = BISTMarket()
    assert market.normalize_symbol("thyao") == "THYAO.IS"
    assert market.normalize_symbol("GARAN.IS") == "GARAN.IS"
    assert market.currency == "TRY"


def test_us_symbol_normalization() -> None:
    market = USEquityMarket()
    assert market.normalize_symbol(" aapl ") == "AAPL"
    assert market.currency == "USD"


def test_gold_symbol_normalization() -> None:
    market = GoldMarket()
    assert market.normalize_symbol("gold") == "XAUUSD"
    assert market.normalize_symbol("XAU/USD") == "XAUUSD"
    assert market.normalize_symbol("gramaltin") == "XAUTRY"


def test_empty_symbol_raises() -> None:
    market = USEquityMarket()
    with pytest.raises(ValueError):
        market.normalize_symbol("  ")


def test_live_data_not_wired() -> None:
    market = BISTMarket()
    with pytest.raises(NotImplementedError):
        market.get_quote("THYAO")
    with pytest.raises(NotImplementedError):
        market.get_history("THYAO")
