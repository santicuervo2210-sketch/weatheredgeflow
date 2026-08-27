from __future__ import annotations

import math
from datetime import datetime, time
from statistics import mean, pstdev
from zoneinfo import ZoneInfo

from app.domain.types import ForecastPoint, ObservationSnapshot, ParsedOutcome, ParsedWeatherMarket, ProbabilityResult
from app.utils.time import utc_now


MODEL_VERSION = "weatheredgeflow-normal-mixture-v1"


class ProbabilityEngine:
    def estimate(
        self,
        market: ParsedWeatherMarket,
        outcome: ParsedOutcome,
        forecasts: list[ForecastPoint],
        observation: ObservationSnapshot | None,
    ) -> ProbabilityResult:
        values = [float(f.value) for f in forecasts if f.value is not None]
        if not values:
            raise ValueError("No valid forecasts")

        lower = outcome.lower_bound
        upper = outcome.upper_bound
        sigma = self._sigma(market, values, observation)
        yes_probability = self._mixture_probability(values, sigma, lower, upper)
        reasons: list[str] = []

        if observation:
            adjusted, reason = self._apply_observation_rules(market, lower, upper, yes_probability, observation)
            yes_probability = adjusted
            if reason:
                reasons.append(reason)

        probability = 1.0 - yes_probability if outcome.side.upper() == "NO" else yes_probability
        probability = max(0.0, min(1.0, probability))
        uncertainty = self._uncertainty(values, sigma, observation)
        confidence = self._confidence(market, values, observation, uncertainty)
        distribution = self._distribution(values, sigma)
        return ProbabilityResult(
            probability=probability,
            uncertainty=uncertainty,
            confidence_score=confidence,
            model_version=MODEL_VERSION,
            distribution=distribution,
            reasons=reasons,
        )

    def _sigma(self, market: ParsedWeatherMarket, values: list[float], observation: ObservationSnapshot | None) -> float:
        base = 2.0 if market.unit == "F" else 1.1
        model_spread = pstdev(values) if len(values) > 1 else base * 0.6
        hours = self._hours_to_local_day_end(market)
        horizon_component = max(0.2, min(1.6, hours / 24.0)) * (1.2 if market.unit == "F" else 0.7)
        obs_discount = 0.72 if observation and observation.observed_at_utc else 1.0
        return max(0.35 if market.unit == "C" else 0.65, (base + model_spread + horizon_component) * obs_discount)

    def _mixture_probability(
        self,
        values: list[float],
        sigma: float,
        lower: float | None,
        upper: float | None,
    ) -> float:
        probs = []
        for value in values:
            lo = -math.inf if lower is None else lower
            hi = math.inf if upper is None else upper
            probs.append(_normal_cdf(hi, value, sigma) - _normal_cdf(lo, value, sigma))
        return max(0.0, min(1.0, mean(probs)))

    def _apply_observation_rules(
        self,
        market: ParsedWeatherMarket,
        lower: float | None,
        upper: float | None,
        probability: float,
        observation: ObservationSnapshot,
    ) -> tuple[float, str | None]:
        if market.weather_metric == "daily_max" and observation.observed_max is not None:
            obs = observation.observed_max
            if upper is not None and obs >= upper:
                return 0.0, "Observed maximum already exceeded bucket upper bound"
            if upper is None and lower is not None and obs >= lower:
                return 1.0, "Observed maximum already reached threshold"
        if market.weather_metric == "daily_min" and observation.observed_min is not None:
            obs = observation.observed_min
            if lower is not None and obs <= lower:
                return 0.0, "Observed minimum already fell below bucket lower bound"
            if lower is None and upper is not None and obs <= upper:
                return 1.0, "Observed minimum already reached threshold"
        return probability, None

    def _uncertainty(self, values: list[float], sigma: float, observation: ObservationSnapshot | None) -> float:
        model_spread = pstdev(values) if len(values) > 1 else sigma
        obs_bonus = 0.02 if observation and observation.observed_at_utc else 0.0
        normalized = min(0.22, (sigma + model_spread) / 45.0)
        return max(0.02, normalized - obs_bonus)

    def _confidence(
        self,
        market: ParsedWeatherMarket,
        values: list[float],
        observation: ObservationSnapshot | None,
        uncertainty: float,
    ) -> float:
        confidence = market.confidence
        confidence += 10.0 if observation and observation.observed_at_utc else -8.0
        confidence += 6.0 if len(values) >= 2 else -8.0
        confidence -= min(25.0, uncertainty * 100.0)
        hours = self._hours_to_local_day_end(market)
        if hours <= 24:
            confidence += 6.0
        if hours > 36:
            confidence -= 18.0
        return max(0.0, min(100.0, confidence))

    def _distribution(self, values: list[float], sigma: float) -> dict[str, float]:
        center = mean(values)
        start = math.floor(center - 5 * sigma)
        end = math.ceil(center + 5 * sigma)
        buckets: dict[str, float] = {}
        total = 0.0
        for temp in range(start, end + 1):
            prob = self._mixture_probability(values, sigma, temp - 0.5, temp + 0.5)
            if prob >= 0.001:
                buckets[str(temp)] = prob
                total += prob
        if total > 0:
            buckets = {key: value / total for key, value in buckets.items()}
        return buckets

    def _hours_to_local_day_end(self, market: ParsedWeatherMarket) -> float:
        tz = ZoneInfo(market.timezone)
        end_local = datetime.combine(market.target_date, time.max, tzinfo=tz)
        return max(0.0, (end_local.astimezone(utc_now().tzinfo) - utc_now()).total_seconds() / 3600)


def _normal_cdf(x: float, mu: float, sigma: float) -> float:
    if x == math.inf:
        return 1.0
    if x == -math.inf:
        return 0.0
    return 0.5 * (1.0 + math.erf((x - mu) / (sigma * math.sqrt(2.0))))

