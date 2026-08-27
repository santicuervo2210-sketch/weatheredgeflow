from __future__ import annotations

from app.domain.types import ObservationSnapshot, ParsedOutcome, ParsedWeatherMarket


class ObservationEngine:
    def blocks_outcome(
        self,
        market: ParsedWeatherMarket,
        outcome: ParsedOutcome,
        observation: ObservationSnapshot | None,
    ) -> tuple[bool, str | None]:
        if observation is None:
            return False, None
        if market.weather_metric == "daily_max" and observation.observed_max is not None:
            if outcome.upper_bound is not None and observation.observed_max >= outcome.upper_bound:
                return True, "OBSERVED_MAX_EXCEEDED_BUCKET"
        if market.weather_metric == "daily_min" and observation.observed_min is not None:
            if outcome.lower_bound is not None and observation.observed_min <= outcome.lower_bound:
                return True, "OBSERVED_MIN_BELOW_BUCKET"
        return False, None

