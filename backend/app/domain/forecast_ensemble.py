from __future__ import annotations

from statistics import mean, pstdev

from app.domain.types import ForecastPoint


class ForecastEnsemble:
    def valid_values(self, forecasts: list[ForecastPoint]) -> list[float]:
        return [float(item.value) for item in forecasts if item.value is not None]

    def mean(self, forecasts: list[ForecastPoint]) -> float | None:
        values = self.valid_values(forecasts)
        return mean(values) if values else None

    def spread(self, forecasts: list[ForecastPoint]) -> float:
        values = self.valid_values(forecasts)
        if len(values) < 2:
            return 0.0
        return pstdev(values)

