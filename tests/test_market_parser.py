from __future__ import annotations

from datetime import date

from app.clients.kalshi import _orderbook_from_payload
from app.clients.weather import extract_twc_daily_observation, extract_twc_hourly_observation, normalize_twc_station
from app.config import AppSettings
from app.domain.edge import calculate_taker_fee
from app.domain.kalshi_parser import KalshiWeatherMarketParser
from app.domain.market_parser import WeatherMarketParser
from app.domain.types import FeeSchedule, ParseFailure, ParsedWeatherMarket
from app.services.scanner import ScannerService
from app.services.settings_service import SettingsService
from tests.fixtures.sample_markets import (
    BUENOS_AIRES_MULTI,
    KALSHI_NYC_HIGH_LESS,
    KALSHI_ORDERBOOK,
    NYC_BINARY,
    TWC_DAILY_NYC_OFFICIAL,
    TWC_HOURLY_NYC_THIN_MARGIN,
    UNSUPPORTED_RAIN,
)


def test_parser_extracts_supported_multi_outcome_market() -> None:
    parsed = WeatherMarketParser().parse(BUENOS_AIRES_MULTI)
    assert isinstance(parsed, ParsedWeatherMarket)
    assert parsed.city == "Buenos Aires"
    assert parsed.country == "Argentina"
    assert parsed.target_date == date(2026, 8, 27)
    assert parsed.weather_metric == "daily_max"
    assert parsed.unit == "C"
    assert len(parsed.outcomes) == 4
    assert parsed.outcomes[1].lower_bound == 18.5
    assert parsed.outcomes[1].upper_bound == 19.5


def test_parser_extracts_binary_threshold_and_station() -> None:
    parsed = WeatherMarketParser().parse(NYC_BINARY)
    assert isinstance(parsed, ParsedWeatherMarket)
    assert parsed.city == "New York City"
    assert parsed.country == "US"
    assert parsed.resolution_station == "KNYC"
    yes = [outcome for outcome in parsed.outcomes if outcome.side == "YES"][0]
    no = [outcome for outcome in parsed.outcomes if outcome.side == "NO"][0]
    assert yes.lower_bound == 80
    assert yes.upper_bound is None
    assert no.lower_bound == 80


def test_parser_prefers_question_unit_when_description_mentions_both_units() -> None:
    market = dict(NYC_BINARY)
    market["question"] = "Will the lowest temperature in Buenos Aires be 11�C on August 26?"
    market["resolutionSource"] = "https://www.weather.gov/wrh/timeseries?site=saez"
    market["description"] = "To toggle between Fahrenheit and Celsius, click the metric units button."
    parsed = WeatherMarketParser().parse(market)
    assert isinstance(parsed, ParsedWeatherMarket)
    assert parsed.unit == "C"


def test_parser_skips_unsupported_weather_variable() -> None:
    parsed = WeatherMarketParser().parse(UNSUPPORTED_RAIN)
    assert isinstance(parsed, ParseFailure)
    assert parsed.reason_code == "UNSUPPORTED_WEATHER_VARIABLE"


def test_kalshi_parser_supports_weather_company_threshold_market() -> None:
    parsed = KalshiWeatherMarketParser().parse(KALSHI_NYC_HIGH_LESS)
    assert isinstance(parsed, ParsedWeatherMarket)
    assert parsed.market_id == "KALSHI:KXHIGHNY-26AUG27-T80"
    assert parsed.city == "New York City"
    assert parsed.weather_metric == "daily_max"
    assert parsed.unit == "F"
    assert parsed.resolution_station == "CLINYC"
    assert parsed.outcomes[0].side == "YES"
    assert parsed.outcomes[0].upper_bound == 80
    assert parsed.outcomes[1].side == "NO"
    assert "above" in parsed.outcomes[1].label


def test_kalshi_parser_derives_no_label_when_api_duplicates_yes_subtitle() -> None:
    market = dict(KALSHI_NYC_HIGH_LESS)
    market["no_sub_title"] = market["yes_sub_title"]
    parsed = KalshiWeatherMarketParser().parse(market)
    assert isinstance(parsed, ParsedWeatherMarket)
    assert parsed.outcomes[1].label == "80F or above"


def test_kalshi_orderbook_normalizes_yes_and_no_asks() -> None:
    yes_book = _orderbook_from_payload(
        KALSHI_ORDERBOOK,
        token_id="KALSHI:KXHIGHNY-26AUG27-T80:YES",
        ticker="KXHIGHNY-26AUG27-T80",
        side="YES",
    )
    no_book = _orderbook_from_payload(
        KALSHI_ORDERBOOK,
        token_id="KALSHI:KXHIGHNY-26AUG27-T80:NO",
        ticker="KXHIGHNY-26AUG27-T80",
        side="NO",
    )
    assert yes_book.best_bid == 0.34
    assert yes_book.best_ask == 0.36
    assert no_book.best_bid == 0.64
    assert no_book.best_ask == 0.66


def test_kalshi_fee_rounds_up_to_next_cent() -> None:
    fee = calculate_taker_fee(100, 0.5, FeeSchedule(True, 0.07, 1, True, 0.0, "kalshi", "ceil_cent"))
    tiny_fee = calculate_taker_fee(1, 0.01, FeeSchedule(True, 0.07, 1, True, 0.0, "kalshi", "ceil_cent"))
    assert fee == 1.75
    assert tiny_fee == 0.01


def test_twc_daily_extracts_official_nyc_report() -> None:
    observation = extract_twc_daily_observation(TWC_DAILY_NYC_OFFICIAL, "CLINYC", date(2026, 8, 27), "F")
    assert observation is not None
    assert observation.provider == "the-weather-company-kalshi"
    assert observation.station == "KNYC"
    assert observation.observed_max == 77
    assert observation.raw["status"] == "official"


def test_twc_hourly_observation_normalizes_clinyc_station() -> None:
    observation = extract_twc_hourly_observation(TWC_HOURLY_NYC_THIN_MARGIN, "CLINYC", date(2026, 8, 27), "F")
    assert observation is not None
    assert normalize_twc_station("CLINYC", "New York City") == "KNYC"
    assert observation.observed_max == 80.1
    assert observation.raw["local_day_complete"] is True


def test_kalshi_twc_guard_blocks_thin_margin_near_strike() -> None:
    market = KalshiWeatherMarketParser().parse(KALSHI_NYC_HIGH_LESS)
    assert isinstance(market, ParsedWeatherMarket)
    observation = extract_twc_hourly_observation(TWC_HOURLY_NYC_THIN_MARGIN, "CLINYC", date(2026, 8, 27), "F")
    assert observation is not None
    scanner = ScannerService(AppSettings(), SettingsService(AppSettings()))
    guard = scanner._official_source_guard(market, market.outcomes[1], observation)
    assert guard is not None
    assert guard[0] == "SOURCE_MARGIN_TOO_THIN"
