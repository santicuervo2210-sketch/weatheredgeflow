from __future__ import annotations

from dataclasses import dataclass

from app.domain.types import RiskDecision


@dataclass(frozen=True)
class RiskLimits:
    bankroll: float
    max_position_percent: float
    max_position_usd: float
    max_total_exposure_percent: float
    max_daily_loss_percent: float
    max_drawdown_percent: float
    min_confidence: float


class RiskManager:
    def assess(
        self,
        *,
        limits: RiskLimits,
        requested_stake: float,
        open_exposure: float,
        grouped_event_exposure: float,
        daily_pnl: float,
        drawdown_percent: float,
        net_edge: float,
        confidence: float,
    ) -> RiskDecision:
        bankroll = max(0.0, limits.bankroll)
        if bankroll <= 0:
            return self._reject("NO_BANKROLL", "Bankroll no disponible.", "No bankroll available.")
        daily_stop = -bankroll * limits.max_daily_loss_percent / 100.0
        if daily_pnl <= daily_stop:
            return self._reject("DAILY_LOSS_LIMIT", "Límite de pérdida diaria alcanzado.", "Daily loss limit reached.")
        if drawdown_percent >= limits.max_drawdown_percent:
            return self._reject("DRAWDOWN_LIMIT", "Límite de drawdown alcanzado.", "Drawdown limit reached.")
        if confidence < limits.min_confidence:
            return self._reject("LOW_CONFIDENCE", "Confidence menor al mínimo configurado.", "Confidence is below configured minimum.")

        individual_cap = min(limits.max_position_usd, bankroll * limits.max_position_percent / 100.0)
        total_cap = bankroll * limits.max_total_exposure_percent / 100.0
        remaining_total = max(0.0, total_cap - open_exposure)
        event_adjustment = max(0.0, grouped_event_exposure - open_exposure)
        max_allowed = min(individual_cap, remaining_total + event_adjustment)
        if max_allowed <= 0:
            return self._reject("EXPOSURE_LIMIT", "Exposición máxima alcanzada.", "Maximum exposure reached.")

        conservative_fraction = min(0.05, max(0.005, net_edge / 4.0)) * max(0.25, confidence / 100.0)
        sized = bankroll * conservative_fraction
        recommended = min(requested_stake, sized, max_allowed)
        if recommended <= 0:
            return self._reject("SIZE_ZERO", "El tamaño recomendado queda en cero.", "Recommended size is zero.")
        return RiskDecision(
            approved=True,
            recommended_stake=round(recommended, 2),
            maximum_allowed_stake=round(max_allowed, 2),
            reason_code="APPROVED",
            reason_es="RiskManager aprobó tamaño conservador.",
            reason_en="RiskManager approved conservative sizing.",
            details={
                "individual_cap": individual_cap,
                "total_cap": total_cap,
                "open_exposure": open_exposure,
                "grouped_event_exposure": grouped_event_exposure,
                "daily_pnl": daily_pnl,
                "drawdown_percent": drawdown_percent,
            },
        )

    def _reject(self, code: str, es: str, en: str) -> RiskDecision:
        return RiskDecision(False, 0.0, 0.0, code, es, en, {})

