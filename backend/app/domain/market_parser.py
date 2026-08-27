from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.clients.polymarket import parse_json_list
from app.domain.types import ParseFailure, ParsedOutcome, ParsedWeatherMarket, WeatherMetric
from app.utils.time import parse_datetime


MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

SOURCE_PATTERNS = (
    ("NOAA", r"\bNOAA\b|National Weather Service|weather\.gov"),
    ("Weather.com", r"weather\.com|The Weather Channel"),
    ("Weather Underground", r"wunderground|weather underground"),
    ("AccuWeather", r"accuweather"),
    ("Open-Meteo", r"open-?meteo"),
    ("Meteostat", r"meteostat"),
    ("Visual Crossing", r"visual crossing"),
)


class WeatherMarketParser:
    def parse(self, market: dict[str, Any]) -> ParsedWeatherMarket | ParseFailure:
        market_id = str(market.get("id") or market.get("marketId") or market.get("conditionId") or "")
        event_id = str(market.get("eventId") or market.get("event_id") or "") or None
        condition_id = str(market.get("conditionId") or market.get("condition_id") or "") or None
        question = str(market.get("question") or market.get("title") or "").strip()
        if not market_id or not question:
            return self._failure(market_id, event_id, question, "UNSUPPORTED_MARKET", market)

        metric = self._metric(question)
        if metric is None:
            return self._failure(market_id, event_id, question, "UNSUPPORTED_WEATHER_VARIABLE", market)

        unit = self._unit(question, market)
        if unit is None:
            return self._failure(market_id, event_id, question, "UNKNOWN_UNIT", market)

        target_date = self._target_date(question, market)
        if target_date is None:
            return self._failure(market_id, event_id, question, "AMBIGUOUS_DATE", market)

        city, country = self._location(question)
        if not city:
            return self._failure(market_id, event_id, question, "AMBIGUOUS_LOCATION", market)

        resolution_rules = self._resolution_rules(market)
        source = self._resolution_source(market, resolution_rules)
        if source is None:
            return self._failure(market_id, event_id, question, "UNKNOWN_RESOLUTION_SOURCE", market)

        outcomes = self._outcomes(market, question, metric, unit)
        if not outcomes:
            return self._failure(market_id, event_id, question, "UNSUPPORTED_OUTCOME", market)

        market_slug = str(market.get("slug") or "") or None
        event_slug = str(market.get("eventSlug") or market.get("event_slug") or "") or None
        event = market.get("event") if isinstance(market.get("event"), dict) else {}
        event_slug = event_slug or (str(event.get("slug") or "") if event else None)
        slug = event_slug or market_slug
        url = str(market.get("url") or "") or None
        if not url and slug:
            url = f"https://polymarket.com/event/{slug}"
        timezone = str(market.get("timezone") or market.get("marketTimezone") or "")
        if not timezone:
            timezone = "America/New_York" if country and country.upper() in {"US", "USA", "UNITED STATES"} else "UTC"

        return ParsedWeatherMarket(
            event_id=event_id,
            market_id=market_id,
            condition_id=condition_id,
            question=question,
            slug=slug,
            polymarket_url=url,
            city=city,
            country=country,
            target_date=target_date,
            timezone=timezone,
            weather_metric=metric,
            unit=unit,
            resolution_source=source,
            resolution_station=self._station(resolution_rules),
            resolution_rules=resolution_rules,
            outcomes=outcomes,
            confidence=self._parse_confidence(source, resolution_rules),
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
            "UNSUPPORTED_MARKET": ("Mercado no compatible con V1.", "Market is not supported by V1."),
            "AMBIGUOUS_LOCATION": ("No pude determinar ciudad/país con confianza.", "Could not determine city/country with confidence."),
            "AMBIGUOUS_DATE": ("No pude determinar la fecha objetivo.", "Could not determine target date."),
            "UNKNOWN_UNIT": ("No pude determinar Celsius/Fahrenheit.", "Could not determine Celsius/Fahrenheit."),
            "UNKNOWN_RESOLUTION_SOURCE": ("No encontré fuente de resolución verificable.", "No verifiable resolution source found."),
            "UNSUPPORTED_WEATHER_VARIABLE": ("Variable meteorológica no soportada en V1.", "Weather variable is not supported in V1."),
            "UNSUPPORTED_OUTCOME": ("Outcome o token no interpretable.", "Outcome or token is not interpretable."),
        }
        es, en = messages.get(reason_code, ("Mercado descartado.", "Market skipped."))
        return ParseFailure(
            market_id=market_id,
            event_id=event_id,
            question=question,
            reason_code=reason_code,
            reason_es=es,
            reason_en=en,
            raw_market=market,
        )

    def _metric(self, question: str) -> WeatherMetric | None:
        q = question.lower()
        if re.search(r"\b(high|highest|max|maximum)\b.*\btemp", q) or re.search(r"\btemp.*\b(high|highest|max|maximum)\b", q):
            return "daily_max"
        if re.search(r"\b(low|lowest|min|minimum)\b.*\btemp", q) or re.search(r"\btemp.*\b(low|lowest|min|minimum)\b", q):
            return "daily_min"
        return None

    def _unit(self, question: str, market: dict[str, Any]) -> str | None:
        question_unit = self._unit_from_text(question)
        if question_unit:
            return question_unit
        haystack = " ".join(
            str(x or "")
            for x in (
                question,
                market.get("description"),
                market.get("resolutionSource"),
                market.get("rules"),
                market.get("outcomes"),
            )
        )
        if re.search(r"°\s*C|�\s*C|\bdegrees\s+Celsius\b|\bCelsius\b|\bCentigrade\b|\bdeg(?:rees)?\s*C\b", haystack, re.I):
            return "C"
        if re.search(r"°\s*F|�\s*F|\bdegrees\s+Fahrenheit\b|\bFahrenheit\b|\bdeg(?:rees)?\s*F\b", haystack, re.I):
            return "F"
        return None

    def _unit_from_text(self, text: str) -> str | None:
        if re.search(r"°\s*C|�\s*C|\bCelsius\b|\bCentigrade\b|\bdeg(?:rees)?\s*C\b", text, re.I):
            return "C"
        if re.search(r"°\s*F|�\s*F|\bFahrenheit\b|\bdeg(?:rees)?\s*F\b", text, re.I):
            return "F"
        return None

    def _target_date(self, question: str, market: dict[str, Any]) -> date | None:
        end_dt = parse_datetime(str(market.get("endDate") or market.get("end_date") or "")) if (market.get("endDate") or market.get("end_date")) else None
        default_year = end_dt.year if end_dt else date.today().year
        match = re.search(
            r"\b("
            + "|".join(MONTHS.keys())
            + r")\.?\s+([0-3]?\d)(?:st|nd|rd|th)?(?:,\s*(20\d{2}))?",
            question,
            re.I,
        )
        if match:
            month = MONTHS[match.group(1).lower().rstrip(".")]
            day = int(match.group(2))
            year = int(match.group(3) or default_year)
            try:
                return date(year, month, day)
            except ValueError:
                return None
        iso = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", question)
        if iso:
            try:
                return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
            except ValueError:
                return None
        if end_dt:
            return end_dt.date()
        return None

    def _location(self, question: str) -> tuple[str | None, str | None]:
        patterns = (
            r"\bin\s+(.+?)\s+on\s+(?:January|February|March|April|May|June|July|August|September|October|November|December|\d{4})",
            r"\bfor\s+(.+?)\s+on\s+(?:January|February|March|April|May|June|July|August|September|October|November|December|\d{4})",
            r"\bat\s+(.+?)\s+on\s+(?:January|February|March|April|May|June|July|August|September|October|November|December|\d{4})",
        )
        for pattern in patterns:
            match = re.search(pattern, question, re.I)
            if not match:
                continue
            raw = re.sub(r"\?$", "", match.group(1)).strip()
            raw = re.sub(r"\s+be(?:\s+.*)?$", "", raw, flags=re.I).strip()
            raw = re.sub(r"\b(the|a|an)\b", "", raw, flags=re.I).strip()
            parts = [part.strip() for part in raw.split(",") if part.strip()]
            if not parts:
                return None, None
            city = parts[0]
            country = parts[1] if len(parts) > 1 else None
            return city, country
        return None, None

    def _resolution_rules(self, market: dict[str, Any]) -> str:
        fields = [
            market.get("resolutionSource"),
            market.get("resolution_source"),
            market.get("rules"),
            market.get("description"),
            market.get("question"),
        ]
        return "\n".join(str(value).strip() for value in fields if value)

    def _resolution_source(self, market: dict[str, Any], rules: str) -> str | None:
        explicit = str(market.get("resolutionSource") or market.get("resolution_source") or "").strip()
        haystack = f"{explicit}\n{rules}"
        for label, pattern in SOURCE_PATTERNS:
            if re.search(pattern, haystack, re.I):
                return explicit or label
        if explicit.startswith("http"):
            return explicit
        return None

    def _station(self, rules: str) -> str | None:
        station_patterns = (
            r"\bsite=([A-Z0-9]{3,6})\b",
            r"\bstation\s*(?:ID|code)?[:\s]+([A-Z0-9]{3,6})\b",
            r"\bweather station\s+([A-Z0-9]{3,6})\b",
            r"\b([K][A-Z0-9]{3})\b",
        )
        for pattern in station_patterns:
            match = re.search(pattern, rules, re.I)
            if match:
                return match.group(1).upper()
        return None

    def _parse_confidence(self, source: str, rules: str) -> float:
        confidence = 75.0
        if source:
            confidence += 8.0
        if self._station(rules):
            confidence += 8.0
        if len(rules) < 50:
            confidence -= 15.0
        return max(0.0, min(100.0, confidence))

    def _outcomes(self, market: dict[str, Any], question: str, metric: WeatherMetric, unit: str) -> list[ParsedOutcome]:
        labels = [str(item) for item in parse_json_list(market.get("outcomes"))]
        token_ids = [str(item) for item in parse_json_list(market.get("clobTokenIds") or market.get("clob_token_ids"))]
        if not labels or not token_ids or len(labels) != len(token_ids):
            return []
        binary_labels = {label.lower() for label in labels}
        if binary_labels <= {"yes", "no"}:
            bounds = self._bounds_from_question(question, unit)
            if bounds is None:
                return []
            lower, upper = bounds
            outcomes = []
            for label, token_id in zip(labels, token_ids, strict=False):
                outcomes.append(
                    ParsedOutcome(
                        token_id=token_id,
                        label=label,
                        side=label.upper(),
                        lower_bound=lower,
                        upper_bound=upper,
                        unit=unit,
                    )
                )
            return outcomes

        parsed: list[ParsedOutcome] = []
        for label, token_id in zip(labels, token_ids, strict=False):
            bounds = self._bounds_from_label(label, unit)
            if bounds is None:
                continue
            parsed.append(
                ParsedOutcome(
                    token_id=token_id,
                    label=label,
                    side="YES",
                    lower_bound=bounds[0],
                    upper_bound=bounds[1],
                    unit=unit,
                )
            )
        return parsed

    def _bounds_from_question(self, question: str, unit: str) -> tuple[float | None, float | None] | None:
        number = self._number_near_unit(question, unit)
        if number is None:
            return None
        q = question.lower()
        if re.search(r"\b(at least|or higher|above|over|exceed|exceeds|reach|reaches|>=)\b", q):
            return number, None
        if re.search(r"\b(or lower|below|under|less than|<=)\b", q):
            return None, number
        if re.search(r"\bbetween\b", q):
            nums = [float(x) for x in re.findall(r"(-?\d+(?:\.\d+)?)", question)]
            if len(nums) >= 2:
                return min(nums[0], nums[1]), max(nums[0], nums[1])
        return number - 0.5, number + 0.5

    def _bounds_from_label(self, label: str, unit: str) -> tuple[float | None, float | None] | None:
        clean = label.replace("−", "-").strip()
        if re.search(r"\b(other|invalid|n/a)\b", clean, re.I):
            return None
        nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", clean)]
        if re.search(r"^\s*(<|under|below|less)", clean, re.I) and nums:
            return None, nums[0]
        if re.search(r"(>|\+|above|over|or higher|at least)", clean, re.I) and nums:
            return nums[0], None
        if len(nums) >= 2:
            return min(nums[0], nums[1]), max(nums[0], nums[1])
        if len(nums) == 1 and (unit in clean.upper() or "°" in clean or "�" in clean):
            return nums[0] - 0.5, nums[0] + 0.5
        return None

    def _number_near_unit(self, text: str, unit: str) -> float | None:
        unit_word = "Fahrenheit" if unit == "F" else "Celsius"
        pattern = r"(-?\d+(?:\.\d+)?)\s*(?:°\s*" + unit + r"|�\s*" + unit + r"|\b" + unit_word + r"\b)"
        matches = re.findall(pattern, text, flags=re.I)
        if not matches:
            matches = re.findall(r"\b(?:at least|above|over|under|below|less than|reach|reaches)\s+(-?\d+(?:\.\d+)?)\b", text, flags=re.I)
        if not matches:
            matches = re.findall(r"\bbe\s+(-?\d+(?:\.\d+)?)\b", text, flags=re.I)
        if not matches:
            return None
        try:
            return float(matches[-1])
        except ValueError:
            return None
