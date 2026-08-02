"""Sinyal değerlendirme motoru (SignalEngine).

Bir veya birden fazla stratejiyi çalıştırır ve sonuçlarını ağırlıklı olarak
birleştirir. Çelişkili sinyallerde veya eşiğin altındaki güçte güvenli şekilde
``HOLD`` döndürür. Kill switch etkinse daima ``HOLD`` döndürür. Bu motor
yalnızca sinyal üretir; hiçbir emir göndermez.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from app.core.kill_switch import KillSwitch, kill_switch
from app.strategies.base import Signal, SignalType, Strategy

# Ağırlıklı skorun sıfır kabul edileceği eşik (kayan nokta gürültüsü).
_ZERO_EPS = 1e-12


@dataclass(frozen=True)
class WeightedComponent:
    """Tek bir stratejinin ağırlığı ve ürettiği sinyal."""

    strategy: str
    weight: float
    signal: Signal


@dataclass(frozen=True)
class CombinedSignal:
    """Ağırlıklı birleştirmenin sonucu."""

    signal: Signal
    components: tuple[WeightedComponent, ...]
    net_score: float  # [-1, 1]; pozitif alış, negatif satış yönlüdür


class SignalEngine:
    """Stratejileri ağırlıklı birleştiren sinyal motoru."""

    def __init__(
        self,
        strategies: Sequence[Strategy],
        *,
        weights: Sequence[float] | None = None,
        min_strength: float = 0.0,
        switch: KillSwitch | None = None,
    ) -> None:
        if not strategies:
            raise ValueError("En az bir strateji gerekli.")
        if weights is None:
            weights = [1.0] * len(strategies)
        if len(weights) != len(strategies):
            raise ValueError("Ağırlık sayısı strateji sayısıyla eşleşmeli.")
        if any((not isfinite(w)) or w <= 0.0 for w in weights):
            raise ValueError("Ağırlıklar pozitif ve sonlu olmalı.")
        total = sum(weights)
        if not isfinite(total) or total <= 0.0:
            raise ValueError("Ağırlık toplamı sıfırdan büyük olmalı.")
        if not 0.0 <= min_strength <= 1.0:
            raise ValueError("min_strength 0 ile 1 arasında olmalı.")

        self.strategies = tuple(strategies)
        self.weights = tuple(float(w) for w in weights)
        self._total_weight = float(total)
        self.min_strength = float(min_strength)
        self._kill_switch = switch or kill_switch

    @property
    def min_bars(self) -> int:
        """Bileşen stratejilerin gerektirdiği azami asgari bar sayısı."""
        return max(s.min_bars for s in self.strategies)

    def _hold(self, symbol: str, reason: str, timestamp: datetime | None) -> Signal:
        return Signal(
            symbol=symbol,
            type=SignalType.HOLD,
            strength=0.0,
            reason=reason,
            strategy="signal_engine",
            timestamp=timestamp,
        )

    def evaluate(
        self,
        symbol: str,
        closes: Sequence[float],
        *,
        timestamp: datetime | None = None,
    ) -> CombinedSignal:
        """Stratejileri çalıştırıp ağırlıklı birleşik sinyali döndürür."""
        # Kill switch etkinse hiçbir yön üretilmez.
        if self._kill_switch.is_engaged:
            return CombinedSignal(
                signal=self._hold(symbol, "Kill switch etkin — HOLD.", timestamp),
                components=(),
                net_score=0.0,
            )

        components: list[WeightedComponent] = []
        score = 0.0
        for strategy, weight in zip(self.strategies, self.weights, strict=True):
            signal = strategy.generate(symbol, closes)
            components.append(
                WeightedComponent(strategy=strategy.name, weight=weight, signal=signal)
            )
            if signal.type is SignalType.BUY:
                score += weight * signal.strength
            elif signal.type is SignalType.SELL:
                score -= weight * signal.strength

        net = score / self._total_weight
        comp_tuple = tuple(components)

        # Çelişkili/nötr sinyal: net sıfıra çok yakınsa güvenli HOLD.
        if abs(net) <= _ZERO_EPS:
            return CombinedSignal(
                signal=self._hold(symbol, "Sinyaller nötr/çelişkili — HOLD.", timestamp),
                components=comp_tuple,
                net_score=0.0,
            )

        strength = min(1.0, abs(net))
        if strength < self.min_strength:
            return CombinedSignal(
                signal=self._hold(
                    symbol,
                    f"Birleşik güç eşiğin altında ({strength:.3f} < {self.min_strength:.3f}).",
                    timestamp,
                ),
                components=comp_tuple,
                net_score=net,
            )

        signal_type = SignalType.BUY if net > 0 else SignalType.SELL
        combined = Signal(
            symbol=symbol,
            type=signal_type,
            strength=strength,
            reason=f"Ağırlıklı net skor {net:+.3f}.",
            strategy="signal_engine",
            timestamp=timestamp,
        )
        return CombinedSignal(signal=combined, components=comp_tuple, net_score=net)
