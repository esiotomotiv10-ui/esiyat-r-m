"""Backtest (geçmişe dönük sınama) motoru.

Stratejileri geçmiş mum verisi üzerinde paper-trading olarak çalıştırır.
Gerçek emir gönderimi hiçbir koşulda yapılmaz; motor yalnızca yerleşik
``PaperBroker`` ve ``ExecutionEngine`` üzerinden çalışır.
"""

from app.backtest.engine import BacktestConfig, BacktestEngine
from app.backtest.result import BacktestResult, Trade

__all__ = ["BacktestEngine", "BacktestConfig", "BacktestResult", "Trade"]
