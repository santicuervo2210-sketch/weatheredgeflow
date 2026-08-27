from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal


WeatherMetric = Literal["daily_max", "daily_min"]


@dataclass(frozen=True)
class ParsedOutcome:
    token_id: str
    label: str
    side: str
    lower_bound: float | None
    upper_bound: float | None
    unit: str


@dataclass(frozen=True)
class ParsedWeatherMarket:
    event_id: str | None
    market_id: str
    condition_id: str | None
    question: str
    slug: str | None
    polymarket_url: str | None
    city: str
    country: str | None
    target_date: date
    timezone: str
    weather_metric: WeatherMetric
    unit: str
    resolution_source: str
    resolution_station: str | None
    resolution_rules: str
    outcomes: list[ParsedOutcome]
    confidence: float
    raw_market: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParseFailure:
    market_id: str
    event_id: str | None
    question: str
    reason_code: str
    reason_es: str
    reason_en: str
    raw_market: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GeoLocation:
    name: str
    country: str | None
    country_code: str | None
    latitude: float
    longitude: float
    timezone: str


@dataclass(frozen=True)
class ForecastPoint:
    provider: str
    model_name: str
    metric: WeatherMetric
    target_date: date
    value: float | None
    unit: str
    issued_at_utc: datetime | None
    fetched_at_utc: datetime
    raw: dict[str, Any]


@dataclass(frozen=True)
class ForecastBundle:
    location: GeoLocation
    forecasts: list[ForecastPoint]
    fetched_at_utc: datetime
    raw: dict[str, Any]


@dataclass(frozen=True)
class ObservationSnapshot:
    provider: str
    station: str | None
    metric_date: date
    observed_max: float | None
    observed_min: float | None
    current_temperature: float | None
    unit: str
    observed_at_utc: datetime | None
    fetched_at_utc: datetime
    raw: dict[str, Any]


@dataclass(frozen=True)
class OrderBookLevel:
    price: float
    size: float


@dataclass(frozen=True)
class OrderBookSnapshot:
    token_id: str
    market: str | None
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    min_order_size: float | None
    tick_size: float | None
    timestamp_utc: datetime
    raw: dict[str, Any]

    @property
    def best_bid(self) -> float | None:
        return max((level.price for level in self.bids), default=None)

    @property
    def best_ask(self) -> float | None:
        return min((level.price for level in self.asks), default=None)

    @property
    def spread(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return max(0.0, self.best_ask - self.best_bid)

    def ask_liquidity_usd_at_or_below(self, price_limit: float) -> float:
        return sum(level.price * level.size for level in self.asks if level.price <= price_limit)


@dataclass(frozen=True)
class FeeSchedule:
    enabled: bool
    rate: float | None
    exponent: float
    taker_only: bool
    rebate_rate: float
    source: str
    rounding: str = "none"


@dataclass(frozen=True)
class ProbabilityResult:
    probability: float
    uncertainty: float
    confidence_score: float
    model_version: str
    distribution: dict[str, float]
    reasons: list[str]


@dataclass(frozen=True)
class EdgeResult:
    action: str
    raw_edge: float
    net_edge: float
    market_probability: float
    executable_price: float
    estimated_fees: float
    spread_cost: float
    slippage: float
    uncertainty_penalty: float
    safety_margin: float
    gross_ev: float
    net_ev: float
    reason_code: str


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    recommended_stake: float
    maximum_allowed_stake: float
    reason_code: str
    reason_es: str
    reason_en: str
    details: dict[str, Any]
