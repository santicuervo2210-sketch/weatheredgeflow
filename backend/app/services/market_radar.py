from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import CryptoSignal, Signal
from app.services.settings_service import RuntimeSettings
from app.utils.time import iso_utc, utc_now


@dataclass(frozen=True)
class RadarCandidate:
    source: str
    venue: str
    id: int
    label: str
    instrument: str
    market: str
    action: str
    status: str
    reason_code: str
    reason_es: str
    reason_en: str
    model_probability: float | None
    market_probability: float | None
    raw_edge: float | None
    net_edge: float | None
    confidence: float | None
    recommended_size: float | None
    url: str | None
    timestamp_utc: str | None
    score: float
    actionable: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "venue": self.venue,
            "id": self.id,
            "label": self.label,
            "instrument": self.instrument,
            "market": self.market,
            "action": self.action,
            "status": self.status,
            "reason_code": self.reason_code,
            "reason_es": self.reason_es,
            "reason_en": self.reason_en,
            "model_probability": self.model_probability,
            "market_probability": self.market_probability,
            "raw_edge": self.raw_edge,
            "net_edge": self.net_edge,
            "confidence": self.confidence,
            "recommended_size": self.recommended_size,
            "url": self.url,
            "timestamp_utc": self.timestamp_utc,
            "score": self.score,
            "actionable": self.actionable,
        }


class MarketRadarService:
    """Ranks all supported signal engines without weakening their own risk filters."""

    def build(self, session: Session, runtime: RuntimeSettings, *, limit: int = 20) -> dict[str, Any]:
        candidates = self._weather_candidates(session, runtime, limit=100) + self._crypto_candidates(session, runtime, limit=100)
        ranked = sorted(candidates, key=lambda item: (item.actionable, item.score), reverse=True)
        actionable = [item for item in ranked if item.actionable]
        watchlist = [item for item in ranked if not item.actionable and item.score > 0]
        best = actionable[0] if actionable else None
        best_watch = watchlist[0] if watchlist else (ranked[0] if ranked else None)
        status = "OPPORTUNITY" if best else "NO_TRADE"
        return {
            "generated_at_utc": iso_utc(utc_now()),
            "status": status,
            "mode": runtime.mode,
            "summary_es": self._summary_es(best, best_watch, len(candidates), len(actionable)),
            "summary_en": self._summary_en(best, best_watch, len(candidates), len(actionable)),
            "best": best.as_dict() if best else None,
            "best_watchlist": best_watch.as_dict() if best_watch else None,
            "actionable_count": len(actionable),
            "candidate_count": len(candidates),
            "items": [item.as_dict() for item in ranked[:limit]],
        }

    def _weather_candidates(self, session: Session, runtime: RuntimeSettings, *, limit: int) -> list[RadarCandidate]:
        signals = session.query(Signal).order_by(Signal.created_at_utc.desc()).limit(limit).all()
        latest: list[Signal] = []
        seen: set[tuple[str, str | None]] = set()
        for signal in signals:
            key = (signal.market_id, signal.token_id)
            if key in seen:
                continue
            seen.add(key)
            latest.append(signal)
        return [self._from_weather(signal, runtime) for signal in latest]

    def _crypto_candidates(self, session: Session, runtime: RuntimeSettings, *, limit: int) -> list[RadarCandidate]:
        signals = session.query(CryptoSignal).order_by(CryptoSignal.timestamp_utc.desc()).limit(limit).all()
        latest: list[CryptoSignal] = []
        seen: set[tuple[str, str, str]] = set()
        for signal in signals:
            key = (signal.venue, signal.symbol, signal.strategy)
            if key in seen:
                continue
            seen.add(key)
            latest.append(signal)
        return [self._from_crypto(signal, runtime) for signal in latest]

    def _from_weather(self, signal: Signal, runtime: RuntimeSettings) -> RadarCandidate:
        edge = signal.net_edge
        score = self._score(edge=edge, confidence=signal.confidence, status=signal.status, min_confidence=runtime.min_confidence)
        size = signal.recommended_stake
        return RadarCandidate(
            source="weather",
            venue="KALSHI" if str(signal.market_id).startswith("KALSHI:") else "POLYMARKET",
            id=signal.id,
            label=f"{signal.city or 'Weather'} {signal.outcome or ''}".strip(),
            instrument=signal.city or "Weather",
            market=signal.question,
            action=signal.action,
            status=signal.status,
            reason_code=signal.reason_code,
            reason_es=signal.reason_es,
            reason_en=signal.reason_en,
            model_probability=signal.model_probability,
            market_probability=signal.market_probability,
            raw_edge=signal.raw_edge,
            net_edge=edge,
            confidence=signal.confidence,
            recommended_size=size,
            url=signal.polymarket_url,
            timestamp_utc=iso_utc(signal.created_at_utc),
            score=score,
            actionable=self._is_actionable(signal.status, signal.action, size, signal.confidence, runtime),
        )

    def _from_crypto(self, signal: CryptoSignal, runtime: RuntimeSettings) -> RadarCandidate:
        edge = signal.net_daily_edge if signal.net_daily_edge is not None else signal.raw_edge
        score = self._score(edge=edge, confidence=signal.confidence, status=signal.status, min_confidence=runtime.min_confidence)
        size = signal.recommended_notional
        return RadarCandidate(
            source="crypto",
            venue=signal.venue,
            id=signal.id,
            label=f"{signal.symbol} {signal.strategy}",
            instrument=signal.symbol,
            market=signal.strategy,
            action=signal.action,
            status=signal.status,
            reason_code=signal.reason_code,
            reason_es=signal.reason_es,
            reason_en=signal.reason_en,
            model_probability=signal.model_probability,
            market_probability=signal.market_probability,
            raw_edge=signal.raw_edge,
            net_edge=edge,
            confidence=signal.confidence,
            recommended_size=size,
            url=self._crypto_url(signal),
            timestamp_utc=iso_utc(signal.timestamp_utc),
            score=score,
            actionable=self._is_actionable(signal.status, signal.action, size, signal.confidence, runtime),
        )

    def _is_actionable(self, status: str, action: str, size: float | None, confidence: float | None, runtime: RuntimeSettings) -> bool:
        return (
            status == "OPPORTUNITY"
            and action != "NO_TRADE"
            and float(size or 0.0) > 0.0
            and float(confidence or 0.0) >= runtime.min_confidence
        )

    def _score(self, *, edge: float | None, confidence: float | None, status: str, min_confidence: float) -> float:
        if status != "OPPORTUNITY" and (confidence is None or confidence < min_confidence):
            return 0.0
        edge_points = max(0.0, float(edge or 0.0)) * 100.0
        confidence_bonus = max(0.0, min(100.0, float(confidence or 0.0))) / 100.0
        status_bonus = 100.0 if status == "OPPORTUNITY" else 0.0
        return round(status_bonus + edge_points + confidence_bonus, 4)

    def _crypto_url(self, signal: CryptoSignal) -> str | None:
        if signal.venue == "BINANCE":
            return f"https://www.binance.com/en/futures/{signal.symbol}"
        if signal.venue == "KALSHI":
            return "https://kalshi.com/markets"
        return None

    def _summary_es(
        self,
        best: RadarCandidate | None,
        best_watch: RadarCandidate | None,
        total: int,
        actionable_count: int,
    ) -> str:
        if best:
            return (
                f"Radar multi-mercado: {actionable_count} oportunidad(es) entre {total} señales. "
                f"Mejor: {best.label} con edge neto {self._fmt_pct(best.net_edge)} y confidence {self._fmt_score(best.confidence)}."
            )
        if best_watch:
            return (
                f"Radar multi-mercado: NO TRADE. Revisadas {total} señales; mejor candidato bloqueado: "
                f"{best_watch.label} ({best_watch.reason_code})."
            )
        return "Radar multi-mercado: NO TRADE. Todavía no hay señales suficientes para rankear."

    def _summary_en(
        self,
        best: RadarCandidate | None,
        best_watch: RadarCandidate | None,
        total: int,
        actionable_count: int,
    ) -> str:
        if best:
            return (
                f"Multi-market radar: {actionable_count} opportunity/opportunities across {total} signals. "
                f"Best: {best.label} with net edge {self._fmt_pct(best.net_edge)} and confidence {self._fmt_score(best.confidence)}."
            )
        if best_watch:
            return (
                f"Multi-market radar: NO TRADE. Reviewed {total} signals; best blocked candidate: "
                f"{best_watch.label} ({best_watch.reason_code})."
            )
        return "Multi-market radar: NO TRADE. Not enough signals to rank yet."

    def _fmt_pct(self, value: float | None) -> str:
        if value is None:
            return "-"
        return f"{value * 100:.1f}%"

    def _fmt_score(self, value: float | None) -> str:
        if value is None:
            return "-"
        return f"{value:.0f}/100"
