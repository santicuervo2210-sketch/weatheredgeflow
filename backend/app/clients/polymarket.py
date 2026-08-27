from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.clients.http import PublicAPIError, RetryableHTTPClient
from app.config import AppSettings
from app.domain.types import FeeSchedule, OrderBookLevel, OrderBookSnapshot
from app.utils.time import parse_datetime, utc_now


logger = logging.getLogger(__name__)

WEATHER_KEYWORDS = (
    "weather",
    "temperature",
    "heat",
    "cold",
    "rain",
    "snow",
    "hurricane",
    "wind",
    "°f",
    "°c",
    "fahrenheit",
    "celsius",
)


class PolymarketClient:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.gamma = RetryableHTTPClient(
            base_url=settings.polymarket_gamma_base_url,
            timeout_seconds=settings.http_timeout_seconds,
            headers={"User-Agent": "WeatherEdgeflow/0.1 public-data-only"},
        )
        self.clob = RetryableHTTPClient(
            base_url=settings.polymarket_clob_base_url,
            timeout_seconds=settings.http_timeout_seconds,
            headers={"User-Agent": "WeatherEdgeflow/0.1 public-data-only"},
        )

    async def close(self) -> None:
        await self.gamma.close()
        await self.clob.close()

    async def health(self) -> dict[str, Any]:
        result = {"gamma": False, "clob": False, "detail": {}}
        try:
            await self.gamma.get("/markets", params={"active": "true", "closed": "false", "limit": 1})
            result["gamma"] = True
        except Exception as exc:  # noqa: BLE001
            result["detail"]["gamma_error"] = str(exc)
        try:
            await self.clob.get("/time")
            result["clob"] = True
        except Exception as exc:  # noqa: BLE001
            result["detail"]["clob_error"] = str(exc)
        return result

    async def get_weather_markets(self, limit: int = 250) -> list[dict[str, Any]]:
        markets = await self._get_weather_tagged_markets(limit=limit)
        tagged_seen = {str(m.get("id") or m.get("conditionId")) for m in markets}
        search_markets = await self._get_active_markets(limit=limit, query="weather")
        markets.extend([m for m in search_markets if str(m.get("id") or m.get("conditionId")) not in tagged_seen])
        if len(markets) < min(20, limit):
            fallback = await self._get_active_markets(limit=limit, query=None)
            seen = {str(m.get("id") or m.get("conditionId")) for m in markets}
            markets.extend([m for m in fallback if str(m.get("id") or m.get("conditionId")) not in seen])
        return [m for m in markets if self._looks_weather_related(m)][:limit]

    async def _get_weather_tagged_markets(self, *, limit: int) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        offset = 0
        page_limit = min(50, max(1, limit))
        while len(items) < limit:
            payload = await self.gamma.get(
                "/events",
                params={
                    "active": "true",
                    "closed": "false",
                    "tag_id": 84,
                    "limit": page_limit,
                    "offset": offset,
                    "order": "endDate",
                    "ascending": "true",
                },
            )
            events = _extract_items(payload)
            if not events:
                break
            for event in events:
                if not isinstance(event, dict):
                    continue
                for market in event.get("markets") or []:
                    if not isinstance(market, dict):
                        continue
                    enriched = dict(market)
                    enriched.setdefault("eventId", event.get("id"))
                    enriched.setdefault("eventSlug", event.get("slug"))
                    enriched.setdefault("eventTitle", event.get("title"))
                    enriched.setdefault("tags", event.get("tags"))
                    enriched.setdefault("event", {"id": event.get("id"), "slug": event.get("slug"), "title": event.get("title")})
                    items.append(enriched)
                    if len(items) >= limit:
                        break
                if len(items) >= limit:
                    break
            if len(events) < page_limit:
                break
            offset += page_limit
        return items

    async def _get_active_markets(self, *, limit: int, query: str | None) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        offset = 0
        page_limit = min(100, max(1, limit))
        while len(items) < limit:
            params: dict[str, Any] = {
                "active": "true",
                "closed": "false",
                "limit": page_limit,
                "offset": offset,
                "order": "endDate",
                "ascending": "true",
            }
            if query:
                params["q"] = query
            try:
                payload = await self.gamma.get("/markets", params=params)
            except PublicAPIError:
                if query:
                    return []
                raise
            page = _extract_items(payload)
            if not page:
                break
            items.extend([m for m in page if isinstance(m, dict)])
            if len(page) < page_limit:
                break
            offset += page_limit
        return items[:limit]

    async def get_market(self, market_id: str) -> dict[str, Any]:
        for path, params in (
            (f"/markets/{market_id}", None),
            ("/markets", {"id": market_id}),
        ):
            try:
                payload = await self.gamma.get(path, params=params)
                items = _extract_items(payload)
                if items:
                    return items[0]
                if isinstance(payload, dict):
                    return payload
            except PublicAPIError:
                continue
        raise PublicAPIError(f"Market not found: {market_id}")

    async def get_orderbook(self, token_id: str) -> OrderBookSnapshot:
        payload = await self.clob.get("/book", params={"token_id": token_id})
        if not isinstance(payload, dict):
            raise PublicAPIError("Invalid orderbook payload", payload=payload)
        if payload.get("error"):
            raise PublicAPIError(str(payload.get("error")), payload=payload)
        return _orderbook_from_payload(payload, token_id=token_id)

    async def get_orderbooks(self, token_ids: list[str]) -> dict[str, OrderBookSnapshot]:
        if not token_ids:
            return {}
        payload = await self.clob.post("/books", json=[{"token_id": token_id} for token_id in token_ids[:500]])
        if not isinstance(payload, list):
            raise PublicAPIError("Invalid batch orderbook payload", payload=payload)
        books: dict[str, OrderBookSnapshot] = {}
        for index, item in enumerate(payload):
            if not isinstance(item, dict) or item.get("error"):
                continue
            requested_token = token_ids[index] if index < len(token_ids) else str(item.get("asset_id") or item.get("token_id") or "")
            book = _orderbook_from_payload(item, token_id=requested_token)
            books[book.token_id] = book
        return books

    async def get_best_bid_ask(self, token_id: str) -> tuple[float | None, float | None]:
        book = await self.get_orderbook(token_id)
        return book.best_bid, book.best_ask

    async def get_spread(self, token_id: str) -> float | None:
        try:
            payload = await self.clob.get("/spread", params={"token_id": token_id})
            if isinstance(payload, dict):
                return _float_or_none(payload.get("spread"))
            return _float_or_none(payload)
        except PublicAPIError:
            book = await self.get_orderbook(token_id)
            return book.spread

    async def get_fee_rate(self, token_id: str) -> FeeSchedule:
        payload = await self.clob.get(f"/fee-rate/{token_id}")
        rate = None
        if isinstance(payload, dict):
            rate = _float_or_none(payload.get("fee_rate") or payload.get("feeRate") or payload.get("rate"))
        else:
            rate = _float_or_none(payload)
        if rate is None:
            raise PublicAPIError("Fee rate unavailable", payload=payload)
        return FeeSchedule(enabled=rate > 0, rate=rate, exponent=1.0, taker_only=True, rebate_rate=0.0, source="clob")

    def fee_schedule_from_market(self, market: dict[str, Any], token_id: str | None = None) -> FeeSchedule | None:
        trading = market.get("trading") if isinstance(market.get("trading"), dict) else {}
        fee_schedule = trading.get("feeSchedule") or trading.get("fee_schedule") or market.get("feeSchedule")
        fees_enabled = _bool_or_none(trading.get("feesEnabled") if "feesEnabled" in trading else market.get("feesEnabled"))
        if isinstance(fee_schedule, str):
            try:
                fee_schedule = json.loads(fee_schedule)
            except json.JSONDecodeError:
                fee_schedule = None
        if isinstance(fee_schedule, dict):
            rate = _float_or_none(fee_schedule.get("rate"))
            return FeeSchedule(
                enabled=bool(fees_enabled) if fees_enabled is not None else bool(rate and rate > 0),
                rate=rate,
                exponent=_float_or_none(fee_schedule.get("exponent")) or 1.0,
                taker_only=bool(fee_schedule.get("takerOnly", fee_schedule.get("taker_only", True))),
                rebate_rate=_float_or_none(fee_schedule.get("rebateRate") or fee_schedule.get("rebate_rate")) or 0.0,
                source="gamma",
            )
        fee_rate = _float_or_none(market.get("feeRate") or market.get("feeRateBps"))
        if fee_rate is not None:
            if fee_rate > 1:
                fee_rate = fee_rate / 10_000.0
            return FeeSchedule(enabled=fee_rate > 0, rate=fee_rate, exponent=1.0, taker_only=True, rebate_rate=0.0, source="gamma")
        return None

    async def get_price_history(self, token_id: str, interval: str = "1d") -> dict[str, Any]:
        payload = await self.clob.get("/prices-history", params={"market": token_id, "interval": interval})
        return payload if isinstance(payload, dict) else {"history": payload}

    def _looks_weather_related(self, market: dict[str, Any]) -> bool:
        haystack = " ".join(
            str(value or "")
            for value in (
                market.get("question"),
                market.get("title"),
                market.get("description"),
                market.get("resolutionSource"),
                market.get("rules"),
                market.get("category"),
                market.get("slug"),
            )
        ).lower()
        tags = market.get("tags") or []
        if isinstance(tags, list):
            haystack += " " + " ".join(str(tag.get("label") or tag.get("slug") or tag) for tag in tags)
        return any(keyword in haystack for keyword in WEATHER_KEYWORDS)


def _extract_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("items", "markets", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        if "id" in payload or "conditionId" in payload:
            return [payload]
    return []


def parse_json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _level(item: Any) -> OrderBookLevel | None:
    if not isinstance(item, dict):
        return None
    price = _float_or_none(item.get("price"))
    size = _float_or_none(item.get("size"))
    if price is None or size is None:
        return None
    return OrderBookLevel(price=price, size=size)


def _orderbook_from_payload(payload: dict[str, Any], *, token_id: str) -> OrderBookSnapshot:
    payload_token = str(payload.get("asset_id") or payload.get("token_id") or token_id)
    bids = [_level(item) for item in payload.get("bids") or []]
    asks = [_level(item) for item in payload.get("asks") or []]
    return OrderBookSnapshot(
        token_id=payload_token,
        market=str(payload.get("market")) if payload.get("market") is not None else None,
        bids=sorted([b for b in bids if b is not None], key=lambda x: x.price, reverse=True),
        asks=sorted([a for a in asks if a is not None], key=lambda x: x.price),
        min_order_size=_float_or_none(payload.get("min_order_size") or payload.get("minOrderSize")),
        tick_size=_float_or_none(payload.get("tick_size") or payload.get("tickSize")),
        timestamp_utc=_parse_book_time(payload.get("timestamp")),
        raw=payload,
    )


def _parse_book_time(value: Any) -> datetime:
    if value is None:
        return utc_now()
    if isinstance(value, (int, float)):
        stamp = float(value)
    else:
        try:
            stamp = float(str(value))
        except ValueError:
            return parse_datetime(str(value)) or utc_now()
    if stamp > 10_000_000_000:
        stamp = stamp / 1000.0
    try:
        return datetime.fromtimestamp(stamp, tz=UTC)
    except (ValueError, OSError):
        return utc_now()


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.lower() in {"true", "1", "yes"}:
            return True
        if value.lower() in {"false", "0", "no"}:
            return False
    return None
