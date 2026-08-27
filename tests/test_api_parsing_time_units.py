from __future__ import annotations

from datetime import UTC, datetime

from app.clients.polymarket import parse_json_list
from app.domain.types import OrderBookLevel, OrderBookSnapshot
from app.utils.time import ensure_utc, local_day_bounds, parse_datetime


def test_parse_json_list_handles_gamma_strings() -> None:
    assert parse_json_list('["Yes","No"]') == ["Yes", "No"]
    assert parse_json_list("Yes,No") == ["Yes", "No"]


def test_best_bid_ask_from_orderbook_levels() -> None:
    book = OrderBookSnapshot(
        token_id="t",
        market="m",
        bids=[OrderBookLevel(0.3, 1), OrderBookLevel(0.4, 1)],
        asks=[OrderBookLevel(0.6, 1), OrderBookLevel(0.5, 1)],
        min_order_size=None,
        tick_size=None,
        timestamp_utc=datetime.now(UTC),
        raw={},
    )
    assert book.best_bid == 0.4
    assert book.best_ask == 0.5
    assert round(book.spread or 0, 4) == 0.1


def test_timezone_day_bounds_are_utc() -> None:
    start, end = local_day_bounds(datetime(2026, 8, 27, 12, tzinfo=UTC), "America/Argentina/Buenos_Aires")
    assert start.tzinfo is not None
    assert end.tzinfo is not None
    assert start.hour == 3
    assert end.hour == 2


def test_parse_datetime_accepts_zulu() -> None:
    parsed = parse_datetime("2026-08-27T12:00:00Z")
    assert parsed == datetime(2026, 8, 27, 12, tzinfo=UTC)
    assert ensure_utc(datetime(2026, 8, 27, 12)).tzinfo == UTC

