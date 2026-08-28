from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.clients.http import RetryableHTTPClient
from app.config import AppSettings


@dataclass(frozen=True)
class BinanceMarketSnapshot:
    symbol: str
    spot_bid: float
    spot_ask: float
    spot_bid_qty: float
    spot_ask_qty: float
    futures_bid: float
    futures_ask: float
    futures_bid_qty: float
    futures_ask_qty: float
    mark_price: float
    index_price: float
    funding_rate: float
    next_funding_time_utc: datetime | None
    raw: dict[str, Any]

    @property
    def spot_mid(self) -> float:
        return (self.spot_bid + self.spot_ask) / 2.0

    @property
    def futures_mid(self) -> float:
        return (self.futures_bid + self.futures_ask) / 2.0

    @property
    def spot_spread(self) -> float:
        return 0.0 if self.spot_mid <= 0 else (self.spot_ask - self.spot_bid) / self.spot_mid

    @property
    def futures_spread(self) -> float:
        return 0.0 if self.futures_mid <= 0 else (self.futures_ask - self.futures_bid) / self.futures_mid

    @property
    def basis(self) -> float:
        return 0.0 if self.index_price <= 0 else (self.mark_price - self.index_price) / self.index_price


class BinancePublicClient:
    def __init__(self, settings: AppSettings) -> None:
        self.spot = RetryableHTTPClient(
            base_url=settings.binance_spot_base_url,
            timeout_seconds=settings.http_timeout_seconds,
            headers={"User-Agent": "WeatherEdgeflow/0.1 crypto-market-data-only"},
        )
        self.futures = RetryableHTTPClient(
            base_url=settings.binance_futures_base_url,
            timeout_seconds=settings.http_timeout_seconds,
            headers={"User-Agent": "WeatherEdgeflow/0.1 crypto-market-data-only"},
        )

    async def close(self) -> None:
        await self.spot.close()
        await self.futures.close()

    async def health(self) -> dict[str, Any]:
        try:
            spot = await self.spot.get("/api/v3/ticker/bookTicker", params={"symbol": "BTCUSDT"})
            futures = await self.futures.get("/fapi/v1/premiumIndex", params={"symbol": "BTCUSDT"})
            return {"ok": bool(spot.get("symbol") == "BTCUSDT" and futures.get("symbol") == "BTCUSDT")}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    async def get_snapshot(self, symbol: str) -> BinanceMarketSnapshot:
        normalized = symbol.upper().strip()
        spot_book = await self.spot.get("/api/v3/ticker/bookTicker", params={"symbol": normalized})
        futures_book = await self.futures.get("/fapi/v1/ticker/bookTicker", params={"symbol": normalized})
        premium = await self.futures.get("/fapi/v1/premiumIndex", params={"symbol": normalized})
        return parse_binance_snapshot(normalized, spot_book, futures_book, premium)


def parse_binance_snapshot(
    symbol: str,
    spot_book: Any,
    futures_book: Any,
    premium: Any,
) -> BinanceMarketSnapshot:
    if not isinstance(spot_book, dict) or not isinstance(futures_book, dict) or not isinstance(premium, dict):
        raise ValueError("Malformed Binance payload")
    next_funding = _datetime_from_ms(_float_or_none(premium.get("nextFundingTime")))
    return BinanceMarketSnapshot(
        symbol=symbol,
        spot_bid=_required_float(spot_book, "bidPrice"),
        spot_ask=_required_float(spot_book, "askPrice"),
        spot_bid_qty=_required_float(spot_book, "bidQty"),
        spot_ask_qty=_required_float(spot_book, "askQty"),
        futures_bid=_required_float(futures_book, "bidPrice"),
        futures_ask=_required_float(futures_book, "askPrice"),
        futures_bid_qty=_required_float(futures_book, "bidQty"),
        futures_ask_qty=_required_float(futures_book, "askQty"),
        mark_price=_required_float(premium, "markPrice"),
        index_price=_required_float(premium, "indexPrice"),
        funding_rate=_required_float(premium, "lastFundingRate"),
        next_funding_time_utc=next_funding,
        raw={"spot_book": spot_book, "futures_book": futures_book, "premium": premium},
    )


def _required_float(payload: dict[str, Any], key: str) -> float:
    value = _float_or_none(payload.get(key))
    if value is None:
        raise ValueError(f"Missing numeric Binance field: {key}")
    return value


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _datetime_from_ms(value: float | None) -> datetime | None:
    if value is None or value <= 0:
        return None
    return datetime.fromtimestamp(value / 1000.0, tz=UTC)
