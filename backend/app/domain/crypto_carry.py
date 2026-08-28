from __future__ import annotations

from dataclasses import dataclass

from app.clients.binance_public import BinanceMarketSnapshot


@dataclass(frozen=True)
class CryptoCarryLimits:
    bankroll: float
    min_net_daily_edge: float
    max_spread: float
    max_basis_risk: float
    min_notional_usd: float
    max_position_usd: float
    max_position_percent: float
    spot_fee_rate: float
    futures_fee_rate: float
    safety_margin: float


@dataclass(frozen=True)
class CryptoCarryDecision:
    symbol: str
    action: str
    status: str
    reason_code: str
    reason_es: str
    reason_en: str
    funding_rate: float
    daily_funding_estimate: float
    annualized_funding_estimate: float
    estimated_costs: float
    basis_risk: float
    net_daily_edge: float
    confidence: float
    recommended_notional: float
    max_notional: float


class CryptoCarryEngine:
    strategy = "SPOT_PERP_CARRY"

    def evaluate(self, snapshot: BinanceMarketSnapshot, limits: CryptoCarryLimits) -> CryptoCarryDecision:
        daily_funding = snapshot.funding_rate * 3.0
        annualized = daily_funding * 365.0
        round_trip_fees = 2.0 * (limits.spot_fee_rate + limits.futures_fee_rate)
        estimated_costs = snapshot.spot_spread + snapshot.futures_spread + round_trip_fees + limits.safety_margin
        basis_risk = abs(snapshot.basis)
        net_daily_edge = daily_funding - estimated_costs
        max_notional = min(limits.max_position_usd, limits.bankroll * limits.max_position_percent / 100.0)
        recommended_notional = max(0.0, min(max_notional, limits.bankroll * 0.10))
        confidence = self._confidence(snapshot, limits, basis_risk)

        if limits.bankroll < limits.min_notional_usd or recommended_notional < limits.min_notional_usd:
            return self._reject(
                snapshot,
                "BELOW_MIN_NOTIONAL",
                "Capital insuficiente para ejecutar spot/perp con tamaño mínimo y costos razonables.",
                "Capital is too small to execute spot/perp with reasonable minimum size and costs.",
                daily_funding,
                annualized,
                estimated_costs,
                basis_risk,
                net_daily_edge,
                confidence,
                recommended_notional,
                max_notional,
            )
        if snapshot.spot_spread > limits.max_spread or snapshot.futures_spread > limits.max_spread:
            return self._reject(
                snapshot,
                "SPREAD_TOO_WIDE",
                "Spread demasiado alto para una estrategia de carry conservadora.",
                "Spread is too wide for a conservative carry strategy.",
                daily_funding,
                annualized,
                estimated_costs,
                basis_risk,
                net_daily_edge,
                confidence,
                recommended_notional,
                max_notional,
            )
        if basis_risk > limits.max_basis_risk:
            return self._reject(
                snapshot,
                "BASIS_RISK_HIGH",
                "La diferencia spot/perp es demasiado grande; el riesgo de base puede dominar el funding.",
                "Spot/perp basis is too large; basis risk may dominate funding.",
                daily_funding,
                annualized,
                estimated_costs,
                basis_risk,
                net_daily_edge,
                confidence,
                recommended_notional,
                max_notional,
            )
        if daily_funding <= 0:
            return self._reject(
                snapshot,
                "FUNDING_NOT_POSITIVE_FOR_SHORT",
                "El funding no favorece una cobertura buy spot + short perp.",
                "Funding does not favor a buy spot + short perp hedge.",
                daily_funding,
                annualized,
                estimated_costs,
                basis_risk,
                net_daily_edge,
                confidence,
                recommended_notional,
                max_notional,
            )
        if net_daily_edge < limits.min_net_daily_edge:
            return self._reject(
                snapshot,
                "COSTS_EXCEED_EDGE",
                "Después de fees, spreads y margen de seguridad no queda edge suficiente.",
                "After fees, spreads, and safety margin there is not enough edge.",
                daily_funding,
                annualized,
                estimated_costs,
                basis_risk,
                net_daily_edge,
                confidence,
                recommended_notional,
                max_notional,
            )

        return CryptoCarryDecision(
            symbol=snapshot.symbol,
            action="BUY_SPOT_SHORT_PERP",
            status="OPPORTUNITY",
            reason_code="CARRY_EDGE_OK",
            reason_es="Funding positivo supera costos estimados y margen de seguridad. Requiere ejecución manual y cobertura exacta.",
            reason_en="Positive funding exceeds estimated costs and safety margin. Requires manual execution and exact hedge.",
            funding_rate=snapshot.funding_rate,
            daily_funding_estimate=daily_funding,
            annualized_funding_estimate=annualized,
            estimated_costs=estimated_costs,
            basis_risk=basis_risk,
            net_daily_edge=net_daily_edge,
            confidence=confidence,
            recommended_notional=recommended_notional,
            max_notional=max_notional,
        )

    def _confidence(self, snapshot: BinanceMarketSnapshot, limits: CryptoCarryLimits, basis_risk: float) -> float:
        confidence = 78.0
        confidence -= min(25.0, snapshot.spot_spread / max(limits.max_spread, 1e-9) * 10.0)
        confidence -= min(25.0, snapshot.futures_spread / max(limits.max_spread, 1e-9) * 10.0)
        confidence -= min(25.0, basis_risk / max(limits.max_basis_risk, 1e-9) * 15.0)
        return max(0.0, min(100.0, confidence))

    def _reject(
        self,
        snapshot: BinanceMarketSnapshot,
        code: str,
        reason_es: str,
        reason_en: str,
        daily_funding: float,
        annualized: float,
        estimated_costs: float,
        basis_risk: float,
        net_daily_edge: float,
        confidence: float,
        recommended_notional: float,
        max_notional: float,
    ) -> CryptoCarryDecision:
        return CryptoCarryDecision(
            symbol=snapshot.symbol,
            action="NO_TRADE",
            status="REJECTED",
            reason_code=code,
            reason_es=reason_es,
            reason_en=reason_en,
            funding_rate=snapshot.funding_rate,
            daily_funding_estimate=daily_funding,
            annualized_funding_estimate=annualized,
            estimated_costs=estimated_costs,
            basis_risk=basis_risk,
            net_daily_edge=net_daily_edge,
            confidence=confidence,
            recommended_notional=0.0,
            max_notional=max_notional,
        )
