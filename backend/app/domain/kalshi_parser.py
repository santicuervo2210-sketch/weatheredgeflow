from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.domain.types import ParseFailure, ParsedOutcome, ParsedWeatherMarket, WeatherMetric
from app.utils.time import parse_datetime


SERIES_INFO: dict[str, dict[str, str]] = {
    "KXHIGHNY": {"city": "New York City", "country": "US", "timezone": "America/New_York"},
    "KXHIGHCHI": {"city": "Chicago", "country": "US", "timezone": "America/Chicago"},
    "KXHIGHMIA": {"city": "Miami", "country": "US", "timezone": "America/New_York"},
    "KXHIGHLAX": {"city": "Los Angeles", "country": "US", "timezone": "America/Los_Angeles"},
    "KXHIGHDEN": {"city": "Denver", "country": "US", "timezone": "America/Denver"},
}


class KalshiWeatherMarketParser:
    def parse(self, market: dict[str, Any]) -> ParsedWeatherMarket | ParseFailure:
        ticker = str(market.get("ticker") or "").strip()
        event_ticker = str(market.get("event_ticker") or "").strip()
        question = str(market.get("title") or "").strip()
        if not ticker or not event_ticker or not question:
            return self._failure(ticker, event_ticker, question, "UNSUPPORTED_MARKET", market)

        series_ticker = str(market.get("series_ticker") or event_ticker.rsplit("-", 1)[0]).upper()
        info = SERIES_INFO.get(series_ticker)
        if info is None:
            return self._failure(ticker, event_ticker, question, "AMBIGUOUS_LOCATION", market)

        metric = self._metric(series_ticker, question)
        if metric is None:
            return self._failure(ticker, event_ticker, question, "UNSUPPORTED_WEATHER_VARIABLE", market)

        target_date = self._target_date(market, question)
        if target_date is None:
            return self._failure(ticker, event_ticker, question, "AMBIGUOUS_DATE", market)

        strike_type = str(market.get("strike_type") or "").lower()
        bounds = self._bounds(market, strike_type)
        if bounds is None:
            return self._failure(ticker, event_ticker, question, "UNSUPPORTED_OUTCOME", market)

        rules = "\n".join(
            value.strip()
            for value in (
                str(market.get("rules_primary") or ""),
                str(market.get("rules_secondary") or ""),
                str(market.get("early_close_condition") or ""),
            )
            if value.strip()
        )
        if "Weather Company" not in rules:
            return self._failure(ticker, event_ticker, question, "UNKNOWN_RESOLUTION_SOURCE", market)

        lower, upper = bounds
        outcomes = [
            ParsedOutcome(
                token_id=f"KALSHI:{ticker}:YES",
                label=str(market.get("yes_sub_title") or "YES"),
                side="YES",
                lower_bound=lower,
                upper_bound=upper,
                unit="F",
            ),
            ParsedOutcome(
                token_id=f"KALSHI:{ticker}:NO",
                label=str(market.get("no_sub_title") or "NO"),
                side="NO",
                lower_bound=lower,
                upper_bound=upper,
                unit="F",
            ),
        ]
        station = self._station(rules)
        url = f"https://kalshi.com/markets/{series_ticker.lower()}"
        return ParsedWeatherMarket(
            event_id=f"KALSHI:{event_ticker}",
            market_id=f"KALSHI:{ticker}",
            condition_id=None,
            question=question,
            slug=ticker,
            polymarket_url=url,
            city=info["city"],
            country=info["country"],
            target_date=target_date,
            timezone=info["timezone"],
            weather_metric=metric,
            unit="F",
            resolution_source="The Weather Company via Kalshi rules",
            resolution_station=station,
            resolution_rules=rules,
            outcomes=outcomes,
            confidence=88.0 if station else 80.0,
            raw_market=market,
        )

    def _failure(
        self,
        market_id: str,
        event_id: str | None,
        question: str,
        reason_code: str,
        market: dict[str, Any],
    ) -> ParseFailure:
        messages = {
            "UNSUPPORTED_MARKET": ("Mercado Kalshi no compatible con V1.", "Kalshi market is not supported by V1."),
            "AMBIGUOUS_LOCATION": ("No pude mapear la serie Kalshi a una ciudad soportada.", "Could not map Kalshi series to a supported city."),
            "AMBIGUOUS_DATE": ("No pude determinar la fecha objetivo.", "Could not determine target date."),
            "UNKNOWN_RESOLUTION_SOURCE": ("Reglas sin fuente Weather Company verificable.", "Rules do not include a verifiable Weather Company source."),
            "UNSUPPORTED_WEATHER_VARIABLE": ("Variable meteorológica no soportada en V1.", "Weather variable is not supported in V1."),
            "UNSUPPORTED_OUTCOME": ("Strike/outcome Kalshi no interpretable.", "Kalshi strike/outcome is not interpretable."),
        }
        es, en = messages.get(reason_code, ("Mercado descartado.", "Market skipped."))
        return ParseFailure(
            market_id=market_id or "unknown",
            event_id=f"KALSHI:{event_id}" if event_id else None,
            question=question,
            reason_code=reason_code,
            reason_es=es,
            reason_en=en,
            raw_market=market,
        )

    def _metric(self, series_ticker: str, question: str) -> WeatherMetric | None:
        q = question.lower()
        if series_ticker.startswith("KXHIGH") or "maximum temperature" in q:
            return "daily_max"
        if series_ticker.startswith("KXLOW") or "minimum temperature" in q:
            return "daily_min"
        return None

    def _target_date(self, market: dict[str, Any], question: str) -> date | None:
        ticker_date = re.search(r"-(\d{2})([A-Z]{3})(\d{1,2})(?:-|$)", str(market.get("event_ticker") or ""))
        if ticker_date:
            months = {
                "JAN": 1,
                "FEB": 2,
                "MAR": 3,
                "APR": 4,
                "MAY": 5,
                "JUN": 6,
                "JUL": 7,
                "AUG": 8,
                "SEP": 9,
                "OCT": 10,
                "NOV": 11,
                "DEC": 12,
            }
            try:
                return date(2000 + int(ticker_date.group(1)), months[ticker_date.group(2)], int(ticker_date.group(3)))
            except (KeyError, ValueError):
                return None
        for key in ("close_time", "occurrence_datetime", "expected_expiration_time"):
            dt = parse_datetime(str(market.get(key) or ""))
            if dt:
                return dt.date()
        return None

    def _bounds(self, market: dict[str, Any], strike_type: str) -> tuple[float | None, float | None] | None:
        floor = _float_or_none(market.get("floor_strike"))
        cap = _float_or_none(market.get("cap_strike"))
        if strike_type == "greater" and floor is not None:
            return floor, None
        if strike_type == "less" and cap is not None:
            return None, cap
        if floor is not None and cap is not None:
            return min(floor, cap), max(floor, cap)
        return None

    def _station(self, rules: str) -> str | None:
        match = re.search(r"\(([A-Z]{3,8})\)", rules)
        return match.group(1) if match else None


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
