"""CSV'den OHLCV mum verisi yükleme.

Beklenen sütunlar: ``timestamp,open,high,low,close,volume``. İsteğe bağlı bir
``symbol`` sütunu bulunabilir; yoksa ``symbol`` parametresi kullanılır.
Zaman damgası ISO 8601 biçiminde olmalıdır (örn. ``2024-01-02`` veya
``2024-01-02T15:30:00``).
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from app.market_data.base import Bar
from app.market_data.models import BarSeries, Timeframe

_REQUIRED_COLUMNS = {"timestamp", "open", "high", "low", "close", "volume"}


def _parse_timestamp(raw: str) -> datetime:
    """ISO 8601 zaman damgasını ayrıştırır."""
    text = raw.strip()
    if not text:
        raise ValueError("timestamp boş olamaz.")
    return datetime.fromisoformat(text)


def _parse_row(row: dict[str, str], default_symbol: str) -> Bar:
    """Tek bir CSV satırını ``Bar`` nesnesine dönüştürür."""
    symbol = (row.get("symbol") or default_symbol).strip()
    if not symbol:
        raise ValueError("Sembol belirtilmeli (parametre veya 'symbol' sütunu).")
    try:
        return Bar(
            symbol=symbol,
            timestamp=_parse_timestamp(row["timestamp"]),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
        )
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Geçersiz CSV satırı: {row!r} ({exc})") from exc


def load_bars_from_csv(
    path: str | Path,
    symbol: str,
    *,
    timeframe: Timeframe = Timeframe.D1,
) -> BarSeries:
    """Bir CSV dosyasından doğrulanmış ``BarSeries`` yükler.

    Args:
        path: CSV dosya yolu.
        symbol: Satırlarda ``symbol`` sütunu yoksa kullanılacak sembol.
        timeframe: Serinin zaman dilimi.

    Raises:
        FileNotFoundError: Dosya bulunamazsa.
        ValueError: Başlık/sütun eksikse veya satırlar geçersizse.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"CSV dosyası bulunamadı: {file_path}")

    with file_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV başlığı (header) bulunamadı.")
        header = {name.strip() for name in reader.fieldnames}
        missing = _REQUIRED_COLUMNS - header
        if missing:
            raise ValueError(f"CSV'de eksik sütunlar: {sorted(missing)}")
        bars = [_parse_row(row, symbol) for row in reader]

    if not bars:
        raise ValueError("CSV veri satırı içermiyor.")

    # BarSeries kronolojik sıra bekler; girdi sırasını garanti etmek için sıralarız.
    bars.sort(key=lambda b: b.timestamp)
    return BarSeries.from_bars(symbol=symbol, timeframe=timeframe, bars=bars)
