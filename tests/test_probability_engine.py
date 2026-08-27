from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

from app.domain.probability import ProbabilityEngine
from app.domain.types import ForecastPoint, ObservationSnapshot, ParsedOutcome
from app.domain.market_parser import WeatherMarketParser
from tests.fixtures.sample_markets import BUENOS_AIRES_MULTI, NYC_BINARY


def _forecast(value: float, unit: str = "C") -> ForecastPoint:
    return ForecastPoint(
        provider="open-meteo",
        model_name="test",
        metric="daily_max",
        target_date=date(2026, 8, 27),
        value=value,
        unit=unit,
        issued_at_utc=datetime(2026, 8, 27, 12, tzinfo=UTC),
        fetched_at_utc=datetime(2026, 8, 27, 12, tzinfo=UTC),
        raw={},
    )


def test_probability_distribution_sums_close_to_one() -> None:
    market = WeatherMarketParser().parse(BUENOS_AIRES_MULTI)
    assert not isinstance(market, type(None))
    outcome = market.outcomes[1]  # type: ignore[union-attr]
    result = ProbabilityEngine().estimate(market, outcome, [_forecast(19.2), _forecast(20.1), _forecast(19.4)], None)  # type: ignore[arg-type]
    assert 0 <= result.probability <= 1
    assert abs(sum(result.distribution.values()) - 1) < 0.001
    assert result.confidence_score > 0


def test_observed_max_blocks_lower_bucket() -> None:
    market = WeatherMarketParser().parse(BUENOS_AIRES_MULTI)
    outcome = market.outcomes[0]  # type: ignore[union-attr]
    observation = ObservationSnapshot(
        provider="open-meteo",
        station=None,
        metric_date=date(2026, 8, 27),
        observed_max=20.0,
        observed_min=14.0,
        current_temperature=20.0,
        unit="C",
        observed_at_utc=datetime(2026, 8, 27, 20, tzinfo=UTC),
        fetched_at_utc=datetime(2026, 8, 27, 20, tzinfo=UTC),
        raw={},
    )
    result = ProbabilityEngine().estimate(market, outcome, [_forecast(19.0), _forecast(19.5)], observation)  # type: ignore[arg-type]
    assert result.probability == 0


def test_binary_no_probability_is_complement() -> None:
    market = WeatherMarketParser().parse(NYC_BINARY)
    no_outcome = [outcome for outcome in market.outcomes if outcome.side == "NO"][0]  # type: ignore[union-attr]
    result = ProbabilityEngine().estimate(market, no_outcome, [_forecast(79, "F"), _forecast(80, "F")], None)  # type: ignore[arg-type]
    yes_result = ProbabilityEngine().estimate(market, replace(no_outcome, side="YES"), [_forecast(79, "F"), _forecast(80, "F")], None)  # type: ignore[arg-type]
    assert abs(result.probability + yes_result.probability - 1) < 0.0001

