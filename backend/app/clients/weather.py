from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.clients.http import PublicAPIError, RetryableHTTPClient
from app.config import AppSettings
from app.domain.types import ForecastBundle, ForecastPoint, GeoLocation, ObservationSnapshot, WeatherMetric
from app.utils.time import ensure_utc, parse_datetime, utc_now


logger = logging.getLogger(__name__)


class WeatherProvider:
    provider_name = "base"

    async def health(self) -> dict[str, Any]:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError


class OpenMeteoProvider(WeatherProvider):
    provider_name = "open-meteo"

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.forecast = RetryableHTTPClient(
            base_url=settings.openmeteo_forecast_base_url,
            timeout_seconds=settings.http_timeout_seconds,
            headers={"User-Agent": "WeatherEdgeflow/0.1 public-data-only"},
        )
        self.geocoding = RetryableHTTPClient(
            base_url=settings.openmeteo_geocoding_base_url,
            timeout_seconds=settings.http_timeout_seconds,
            headers={"User-Agent": "WeatherEdgeflow/0.1 public-data-only"},
        )

    async def close(self) -> None:
        await self.forecast.close()
        await self.geocoding.close()

    async def health(self) -> dict[str, Any]:
        try:
            await self.forecast.get("/forecast", params={"latitude": 0, "longitude": 0, "current": "temperature_2m"})
            return {"ok": True}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    async def geocode(self, city: str, country: str | None = None) -> GeoLocation | None:
        payload = await self.geocoding.get(
            "/search",
            params={"name": city, "count": 10, "language": "en", "format": "json"},
        )
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            return None
        normalized_country = (country or "").strip().lower()
        ranked = []
        for item in results:
            if not isinstance(item, dict):
                continue
            score = 0
            if normalized_country and normalized_country in str(item.get("country") or "").lower():
                score += 10
            if normalized_country and normalized_country == str(item.get("country_code") or "").lower():
                score += 10
            score += int(item.get("population") or 0) / 10_000_000
            ranked.append((score, item))
        if not ranked:
            return None
        item = sorted(ranked, key=lambda pair: pair[0], reverse=True)[0][1]
        try:
            return GeoLocation(
                name=str(item.get("name") or city),
                country=item.get("country"),
                country_code=item.get("country_code"),
                latitude=float(item["latitude"]),
                longitude=float(item["longitude"]),
                timezone=str(item.get("timezone") or self.settings.user_timezone),
            )
        except (KeyError, TypeError, ValueError):
            return None

    async def fetch_bundle(
        self,
        location: GeoLocation,
        metric: WeatherMetric,
        target_date: date,
        unit: str,
    ) -> ForecastBundle:
        unit_param = "fahrenheit" if unit.upper() == "F" else "celsius"
        models = ["best_match", "gfs_global", "ecmwf_ifs025", "icon_global"]
        forecasts: list[ForecastPoint] = []
        raw: dict[str, Any] = {"models": {}}
        for model_name in models:
            params = {
                "latitude": location.latitude,
                "longitude": location.longitude,
                "daily": "temperature_2m_max,temperature_2m_min",
                "hourly": "temperature_2m",
                "current": "temperature_2m",
                "temperature_unit": unit_param,
                "timezone": location.timezone,
                "start_date": target_date.isoformat(),
                "end_date": target_date.isoformat(),
            }
            if model_name != "best_match":
                params["models"] = model_name
            try:
                payload = await self.forecast.get("/forecast", params=params)
            except PublicAPIError as exc:
                raw["models"][model_name] = {"error": str(exc)}
                continue
            raw["models"][model_name] = payload
            value = _daily_value(payload, metric, target_date)
            fetched = utc_now()
            forecasts.append(
                ForecastPoint(
                    provider=self.provider_name,
                    model_name=model_name,
                    metric=metric,
                    target_date=target_date,
                    value=value,
                    unit=unit.upper(),
                    issued_at_utc=_issued_at(payload),
                    fetched_at_utc=fetched,
                    raw=payload if isinstance(payload, dict) else {"payload": payload},
                )
            )
        return ForecastBundle(location=location, forecasts=forecasts, fetched_at_utc=utc_now(), raw=raw)

    async def fetch_observation(
        self,
        location: GeoLocation,
        metric_date: date,
        unit: str,
    ) -> ObservationSnapshot:
        unit_param = "fahrenheit" if unit.upper() == "F" else "celsius"
        payload = await self.forecast.get(
            "/forecast",
            params={
                "latitude": location.latitude,
                "longitude": location.longitude,
                "hourly": "temperature_2m",
                "current": "temperature_2m",
                "temperature_unit": unit_param,
                "timezone": location.timezone,
                "start_date": metric_date.isoformat(),
                "end_date": metric_date.isoformat(),
            },
        )
        now_local = datetime.now(ZoneInfo(location.timezone))
        hourly = payload.get("hourly") if isinstance(payload, dict) else {}
        times = hourly.get("time") if isinstance(hourly, dict) else []
        temps = hourly.get("temperature_2m") if isinstance(hourly, dict) else []
        observed_values: list[float] = []
        observed_at = None
        if isinstance(times, list) and isinstance(temps, list):
            for time_str, temp in zip(times, temps, strict=False):
                try:
                    local_dt = datetime.fromisoformat(str(time_str)).replace(tzinfo=ZoneInfo(location.timezone))
                    if local_dt.date() == metric_date and local_dt <= now_local and temp is not None:
                        observed_values.append(float(temp))
                        observed_at = ensure_utc(local_dt)
                except (TypeError, ValueError):
                    continue
        current = None
        current_time = None
        if isinstance(payload, dict) and isinstance(payload.get("current"), dict):
            current = _float_or_none(payload["current"].get("temperature_2m"))
            current_time = parse_datetime(str(payload["current"].get("time"))) if payload["current"].get("time") else None
        return ObservationSnapshot(
            provider=self.provider_name,
            station=None,
            metric_date=metric_date,
            observed_max=max(observed_values) if observed_values else current,
            observed_min=min(observed_values) if observed_values else current,
            current_temperature=current,
            unit=unit.upper(),
            observed_at_utc=observed_at or current_time,
            fetched_at_utc=utc_now(),
            raw=payload if isinstance(payload, dict) else {"payload": payload},
        )


class NOAAProvider(WeatherProvider):
    provider_name = "noaa"

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.client = RetryableHTTPClient(
            base_url=settings.noaa_base_url,
            timeout_seconds=settings.http_timeout_seconds,
            headers={
                "User-Agent": "WeatherEdgeflow/0.1 contact: local-user",
                "Accept": "application/geo+json, application/json",
            },
        )

    async def close(self) -> None:
        await self.client.close()

    async def health(self) -> dict[str, Any]:
        try:
            await self.client.get("/points/38.8894,-77.0352")
            return {"ok": True}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    async def fetch_observation(
        self,
        location: GeoLocation,
        metric_date: date,
        unit: str,
    ) -> ObservationSnapshot | None:
        if location.country_code != "US":
            return None
        points = await self.client.get(f"/points/{location.latitude:.4f},{location.longitude:.4f}")
        props = points.get("properties") if isinstance(points, dict) else {}
        stations_url = props.get("observationStations") if isinstance(props, dict) else None
        if not stations_url:
            return None
        stations_payload = await self.client.get(stations_url.replace(self.settings.noaa_base_url, ""))
        features = stations_payload.get("features") if isinstance(stations_payload, dict) else []
        if not features:
            return None
        station_id = str(features[0].get("properties", {}).get("stationIdentifier") or "")
        observations = await self.client.get(f"/stations/{station_id}/observations")
        temps: list[float] = []
        observed_at = None
        for feature in observations.get("features", []) if isinstance(observations, dict) else []:
            props = feature.get("properties", {})
            timestamp = parse_datetime(props.get("timestamp"))
            temp_c = props.get("temperature", {}).get("value")
            if timestamp is None or temp_c is None:
                continue
            if timestamp.astimezone(ZoneInfo(location.timezone)).date() != metric_date:
                continue
            value = float(temp_c)
            if unit.upper() == "F":
                value = value * 9 / 5 + 32
            temps.append(value)
            observed_at = timestamp
        if not temps:
            return None
        return ObservationSnapshot(
            provider=self.provider_name,
            station=station_id,
            metric_date=metric_date,
            observed_max=max(temps),
            observed_min=min(temps),
            current_temperature=temps[0],
            unit=unit.upper(),
            observed_at_utc=observed_at,
            fetched_at_utc=utc_now(),
            raw=observations if isinstance(observations, dict) else {"payload": observations},
        )


def _daily_value(payload: Any, metric: WeatherMetric, target_date: date) -> float | None:
    if not isinstance(payload, dict):
        return None
    daily = payload.get("daily")
    if not isinstance(daily, dict):
        return None
    dates = daily.get("time")
    key = "temperature_2m_max" if metric == "daily_max" else "temperature_2m_min"
    values = daily.get(key)
    if not isinstance(dates, list) or not isinstance(values, list):
        return None
    for day, value in zip(dates, values, strict=False):
        if str(day) == target_date.isoformat() and value is not None:
            return _float_or_none(value)
    return None


def _issued_at(payload: Any) -> datetime | None:
    if isinstance(payload, dict):
        generation_ms = payload.get("generationtime_ms")
        current = payload.get("current")
        if isinstance(current, dict) and current.get("time"):
            return parse_datetime(str(current.get("time")))
        if generation_ms is not None:
            return utc_now()
    return None


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
