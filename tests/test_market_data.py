"""Piyasa verisi modelleri, CSV yükleyici ve depo testleri."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.market_data import (
    BarSeries,
    InMemoryBarRepository,
    Timeframe,
    load_bars_from_csv,
)
from app.market_data.base import Bar


def _bar(symbol: str, day: int, close: float) -> Bar:
    return Bar(
        symbol=symbol,
        timestamp=datetime(2024, 1, 1) + timedelta(days=day),
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=1000,
    )


def _series(symbol: str = "AAPL", n: int = 5) -> BarSeries:
    bars = [_bar(symbol, i, 100 + i) for i in range(n)]
    return BarSeries.from_bars(symbol, Timeframe.D1, bars)


# --- BarSeries ---


def test_barseries_properties() -> None:
    series = _series(n=3)
    assert len(series) == 3
    assert list(series.closes) == [100.0, 101.0, 102.0]
    assert series.highs[0] == 101.0
    assert series.lows[0] == 99.0


def test_barseries_rejects_empty() -> None:
    with pytest.raises(ValueError):
        BarSeries.from_bars("AAPL", Timeframe.D1, [])


def test_barseries_rejects_unsorted() -> None:
    bars = [_bar("AAPL", 2, 100), _bar("AAPL", 1, 101)]
    with pytest.raises(ValueError, match="artan"):
        BarSeries.from_bars("AAPL", Timeframe.D1, bars)


def test_barseries_rejects_symbol_mismatch() -> None:
    bars = [_bar("AAPL", 0, 100), _bar("MSFT", 1, 101)]
    with pytest.raises(ValueError, match="uyuşmuyor"):
        BarSeries.from_bars("AAPL", Timeframe.D1, bars)


def test_barseries_rejects_inconsistent_ohlc() -> None:
    bad = Bar(
        symbol="AAPL",
        timestamp=datetime(2024, 1, 1),
        open=100,
        high=99,  # high < open → tutarsız
        low=98,
        close=100,
        volume=10,
    )
    with pytest.raises(ValueError, match="OHLC"):
        BarSeries.from_bars("AAPL", Timeframe.D1, [bad])


# --- CSV loader ---


def _write_csv(path: Path, rows: list[str], header: str | None = None) -> None:
    head = header if header is not None else "timestamp,open,high,low,close,volume"
    path.write_text("\n".join([head, *rows]) + "\n", encoding="utf-8")


def test_load_bars_from_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "aapl.csv"
    _write_csv(
        csv_path,
        [
            "2024-01-03,101,103,100,102,1500",
            "2024-01-01,100,101,99,100,1000",
            "2024-01-02,100,102,99,101,1200",
        ],
    )
    series = load_bars_from_csv(csv_path, "AAPL", timeframe=Timeframe.D1)
    assert len(series) == 3
    # CSV sırasız verilse de kronolojik sıralanır.
    assert [b.timestamp.day for b in series] == [1, 2, 3]
    assert series.symbol == "AAPL"


def test_load_bars_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_bars_from_csv("/nonexistent/path.csv", "AAPL")


def test_load_bars_missing_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad.csv"
    _write_csv(csv_path, ["2024-01-01,1,2"], header="timestamp,open,high")
    with pytest.raises(ValueError, match="eksik sütunlar"):
        load_bars_from_csv(csv_path, "AAPL")


def test_load_bars_invalid_row(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad_row.csv"
    _write_csv(csv_path, ["2024-01-01,abc,101,99,100,1000"])
    with pytest.raises(ValueError, match="Geçersiz CSV satırı"):
        load_bars_from_csv(csv_path, "AAPL")


# --- Repository ---


def test_repository_save_and_get() -> None:
    repo = InMemoryBarRepository()
    series = _series("AAPL")
    repo.save(series)
    assert repo.get("AAPL", Timeframe.D1) is series
    assert repo.get("MSFT", Timeframe.D1) is None
    assert repo.symbols() == ["AAPL"]


def test_repository_get_range() -> None:
    repo = InMemoryBarRepository()
    repo.save(_series("AAPL", n=5))
    subset = repo.get_range(
        "AAPL",
        Timeframe.D1,
        start=datetime(2024, 1, 2),
        end=datetime(2024, 1, 4),
    )
    assert subset is not None
    assert len(subset) == 3
    assert subset[0].timestamp == datetime(2024, 1, 2)


def test_repository_get_range_empty() -> None:
    repo = InMemoryBarRepository()
    repo.save(_series("AAPL", n=3))
    subset = repo.get_range("AAPL", Timeframe.D1, start=datetime(2030, 1, 1))
    assert subset is None
