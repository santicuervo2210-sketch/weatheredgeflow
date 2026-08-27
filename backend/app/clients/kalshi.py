from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.clients.http import PublicAPIError, RetryableHTTPClient
from app.config import AppSettings
from app.domain.kalshi_parser import SERIES_INFO
from app.domain.types import FeeSchedule, OrderBookLevel, OrderBookSnapshot
from app.utils.time import parse_datetime, utc_now


logger = logging.getLogger(__name__)


class KalshiClient:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.client = RetryableHTTPClient(
            base_url=settings.kalshi_base_url,
            timeout_seconds=settings.http_timeout_seconds,
            headers={"User-Agent": "WeatherEdgeflow/0.1 public-data-only"},
        )

    async def close(self) -> None:
        await self.client.close()

    async def health(self) -> dict[str, Any]:
        try:
            payload = await self.client.get("/markets", params={"series_ticker": "KXHIGHNY", "status": "open", "limit": 1})
            return {"ok": bool(_extract_markets(payload)), "detail": {"series": "KXHIGHNY"}}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    def series_tickers(self) -> list[str]:
        configured = [item.strip().upper() for item in self.settings.kalshi_series_tickers.split(",") if item.strip()]
        return [ticker for ticker in configured if ticker in SERIES_INFO]

    async def get_weather_markets(self, limit: int = 250) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for series_ticker in self.series_tickers():
            cursor: str | None = None
            while len(items) < limit:
                params: dict[str, Any] = {"series_ticker": series_ticker, "status": "open", "limit": min(100, limit)}
                if cursor:
                    params["cursor"] = cursor
                payload = await self.client.get("/markets", params=params)
                page = _extract_markets(payload)
                for market in page:
                    market["series_ticker"] = series_ticker
                    items.append(market)
                    if len(items) >= limit:
                        break
                cursor = payload.get("cursor") if isinstance(payload, dict) else None
                if not page or not cursor:
                    break
        return items[:limit]

    async def get_market(self, market_id: str) -> dict[str, Any]:
        ticker = _ticker_from_market_id(market_id)
        payload = await self.client.get(f"/markets/{ticker}")
        if isinstance(payload, dict) and isinstance(payload.get("market"), dict):
            market = payload["market"]
            series = str(market.get("event_ticker") or "").rsplit("-", 1)[0]
            market["series_ticker"] = series
            return market
        raise PublicAPIError(f"Kalshi market not found: {market_id}", payload=payload)

    async def get_orderbook(self, token_id: str) -> OrderBookSnapshot:
        ticker, side = _ticker_side_from_token_id(token_id)
        payload = await self.client.get(f"/markets/{ticker}/orderbook")
        return _orderbook_from_payload(payload, token_id=token_id, ticker=ticker, side=side)

    async def get_orderbooks(self, token_ids: list[str]) -> dict[str, OrderBookSnapshot]:
        books: dict[str, OrderBookSnapshot] = {}
        by_ticker: dict[str, list[tuple[str, str]]] = {}
        for token_id in token_ids:
            ticker, side = _ticker_side_from_token_id(token_id)
            by_ticker.setdefault(ticker, []).append((token_id, side))
        for ticker, sides in by_ticker.items():
            payload = await self.client.get(f"/markets/{ticker}/orderbook")
            for token_id, side in sides:
                books[token_id] = _orderbook_from_payload(payload, token_id=token_id, ticker=ticker, side=side)
        return books

    async def get_best_bid_ask(self, token_id: str) -> tuple[float | None, float | None]:
        book = await self.get_orderbook(token_id)
        return book.best_bid, book.best_ask

    async def get_spread(self, token_id: str) -> float | None:
        book = await self.get_orderbook(token_id)
        return book.spread

    async def get_fee_rate(self, token_id: str) -> FeeSchedule:
        return self.fee_schedule_from_market({}, token_id) or FeeSchedule(
            enabled=True,
            rate=0.07,
            exponent=1.0,
            taker_only=True,
            rebate_rate=0.0,
            source="kalshi-official-fee-schedule",
            rounding="ceil_cent",
        )

    def fee_schedule_from_market(self, market: dict[str, Any], token_id: str | None = None) -> FeeSchedule | None:
        return FeeSchedule(
            enabled=True,
            rate=0.07,
            exponent=1.0,
            taker_only=True,
            rebate_rate=0.0,
            source="kalshi-official-fee-schedule",
            rounding="ceil_cent",
        )

    async def get_price_history(self, token_id: str, interval: str = "1d") -> dict[str, Any]:
        ticker, _side = _ticker_side_from_token_id(token_id)
        return await self.client.get(f"/markets/{ticker}/trades", params={"limit": 100})


def _extract_markets(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("markets"), list):
        return [item for item in payload["markets"] if isinstance(item, dict)]
    return []


def _ticker_from_market_id(market_id: str) -> str:
    return market_id.replace("KALSHI:", "", 1)


def _ticker_side_from_token_id(token_id: str) -> tuple[str, str]:
    parts = token_id.split(":")
    if len(parts) == 3 and parts[0] == "KALSHI":
        return parts[1], parts[2].upper()
    raise PublicAPIError(f"Invalid Kalshi token id: {token_id}")


def _orderbook_from_payload(payload: Any, *, token_id: str, ticker: str, side: str) -> OrderBookSnapshot:
    if not isinstance(payload, dict):
        raise PublicAPIError("Invalid Kalshi orderbook payload", payload=payload)
    book = payload.get("orderbook_fp") if isinstance(payload.get("orderbook_fp"), dict) else payload.get("orderbook")
    if not isinstance(book, dict):
        raise PublicAPIError("Kalshi orderbook missing orderbook_fp", payload=payload)
    yes_bids = _levels(book.get("yes_dollars") or [])
    no_bids = _levels(book.get("no_dollars") or [])
    if side == "YES":
        bids = yes_bids
        asks = _complement_asks(no_bids)
    else:
        bids = no_bids
        asks = _complement_asks(yes_bids)
    return OrderBookSnapshot(
        token_id=token_id,
        market=ticker,
        bids=sorted(bids, key=lambda x: x.price, reverse=True),
        asks=sorted(asks, key=lambda x: x.price),
        min_order_size=1.0,
        tick_size=0.01,
        timestamp_utc=utc_now(),
        raw=payload,
    )


def _levels(items: Any) -> list[OrderBookLevel]:
    levels: list[OrderBookLevel] = []
    if not isinstance(items, list):
        return levels
    for item in items:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            price = _float_or_none(item[0])
            size = _float_or_none(item[1])
        elif isinstance(item, dict):
            price = _float_or_none(item.get("price") or item.get("price_dollars"))
            size = _float_or_none(item.get("size") or item.get("count") or item.get("count_fp"))
        else:
            continue
        if price is None or size is None or size <= 0 or price <= 0 or price >= 1:
            continue
        levels.append(OrderBookLevel(price=price, size=size))
    return levels


def _complement_asks(opposite_bids: list[OrderBookLevel]) -> list[OrderBookLevel]:
    return [OrderBookLevel(price=round(1.0 - level.price, 4), size=level.size) for level in opposite_bids if 0 < 1.0 - level.price < 1]


def _parse_book_time(value: Any) -> datetime:
    dt = parse_datetime(str(value or ""))
    if dt:
        return dt
    return datetime.now(UTC)


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
