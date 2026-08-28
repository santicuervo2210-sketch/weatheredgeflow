from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.clients.binance_public import parse_klines
from app.domain.crypto_barrier import (
    CryptoBarrierEngine,
    KalshiCryptoMarket,
    annualized_realized_vol,
    barrier_touch_probability,
    best_side,
    parse_kalshi_btc_market,
    parse_kalshi_crypto_market,
    short_direction_probability,
)


def _market(
    *,
    strike: float = 110_000.0,
    direction: str = "above",
    yes_bid: float | None = 0.19,
    yes_ask: float | None = 0.20,
    no_bid: float | None = 0.79,
    no_ask: float | None = 0.80,
) -> KalshiCryptoMarket:
    return KalshiCryptoMarket(
        ticker="KXBTCMAXY-26DEC31-109999.99",
        event_ticker="KXBTCMAXY-26DEC31",
        title="Will Bitcoin be above $109,999.99 by Dec 31, 2026 at 11:59 PM ET?",
        symbol="BTCUSDT",
        market_type="barrier",
        direction=direction,
        strike=strike,
        close_time_utc=datetime.now(tz=UTC) + timedelta(days=30),
        start_time_utc=None,
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        no_bid=no_bid,
        no_ask=no_ask,
        raw={"ticker": "KXBTCMAXY-26DEC31-109999.99"},
    )


def _closes(count: int = 336, start: float = 100_000.0, hourly_return: float = 0.001) -> list[float]:
    values = [start]
    for index in range(1, count):
        direction = 1 if index % 2 == 0 else -1
        values.append(values[-1] * (1.0 + direction * hourly_return))
    return values


def test_parse_kalshi_btc_barrier_market() -> None:
    parsed = parse_kalshi_btc_market(
        {
            "ticker": "KXBTCMAXY-26DEC31-109999.99",
            "event_ticker": "KXBTCMAXY-26DEC31",
            "title": "Will Bitcoin be above $109,999.99 by Dec 31, 2026 at 11:59 PM ET?",
            "close_time": "2026-12-31T23:59:00Z",
            "yes_bid_dollars": "0.19",
            "yes_ask_dollars": "0.23",
            "no_bid_dollars": "0.76",
            "no_ask_dollars": "0.80",
        }
    )

    assert parsed is not None
    assert parsed.direction == "above"
    assert parsed.symbol == "BTCUSDT"
    assert parsed.market_type == "barrier"
    assert parsed.strike == 109_999.99
    assert parsed.yes_ask == 0.23


def test_parse_kalshi_btc_market_rejects_non_btc_or_missing_expiry() -> None:
    assert parse_kalshi_btc_market({"title": "Will Ethereum be above $5,000?"}) is None
    assert parse_kalshi_btc_market({"title": "Will Bitcoin be above $100,000?"}) is None


def test_parse_kalshi_xrp_short_direction_market() -> None:
    parsed = parse_kalshi_crypto_market(
        {
            "ticker": "KXXRP15M-26AUG281300-00",
            "event_ticker": "KXXRP15M-26AUG281300",
            "title": "XRP price up in next 15 mins?",
            "close_time": (datetime.now(tz=UTC) + timedelta(minutes=10)).isoformat(),
            "yes_bid_dollars": "0.60",
            "yes_ask_dollars": "0.62",
            "no_bid_dollars": "0.38",
            "no_ask_dollars": "0.40",
        }
    )

    assert parsed is not None
    assert parsed.symbol == "XRPUSDT"
    assert parsed.market_type == "directional"
    assert parsed.direction == "up"
    assert parsed.start_time_utc is not None


def test_parse_klines_rejects_malformed_or_short_payload() -> None:
    with pytest.raises(ValueError):
        parse_klines({"not": "a list"})
    with pytest.raises(ValueError):
        parse_klines([[1, "1", "1", "1", "1"]])


def test_parse_klines_extracts_close_prices() -> None:
    rows = parse_klines([[idx, "100", "105", "95", str(100 + idx)] for idx in range(24)])
    assert len(rows) == 24
    assert rows[-1]["close"] == 123


def test_realized_vol_requires_enough_history() -> None:
    with pytest.raises(ValueError):
        annualized_realized_vol([100, 101])


def test_barrier_probability_direction_rules() -> None:
    above_probability = barrier_touch_probability(
        spot_price=100_000,
        barrier=110_000,
        annualized_vol=0.5,
        years=30 / 365,
        direction="above",
    )
    below_probability = barrier_touch_probability(
        spot_price=100_000,
        barrier=90_000,
        annualized_vol=0.5,
        years=30 / 365,
        direction="below",
    )

    assert 0 < above_probability < 1
    assert 0 < below_probability < 1
    assert barrier_touch_probability(spot_price=111_000, barrier=110_000, annualized_vol=0.5, years=0.1, direction="above") == 1.0


def test_short_direction_probability_uses_elapsed_window() -> None:
    closes = [1.0 + index * 0.0001 for index in range(180)]
    probability = short_direction_probability(
        spot_price=1.03,
        minute_closes=closes,
        close_time_utc=datetime.now(tz=UTC) + timedelta(minutes=5),
        start_time_utc=datetime.now(tz=UTC) - timedelta(minutes=10),
    )

    assert probability > 0.5


def test_best_side_can_select_no() -> None:
    side, executable, _, _, raw_edge = best_side(0.20, _market(yes_bid=0.18, yes_ask=0.22))
    assert side == "BUY_NO"
    assert executable == 0.80
    assert raw_edge == 0.0


def test_crypto_barrier_rejects_wide_spread() -> None:
    decision = CryptoBarrierEngine().evaluate(
        _market(strike=101_000, yes_bid=0.10, yes_ask=0.35, no_bid=0.50, no_ask=0.90),
        spot_price=100_000,
        hourly_closes=_closes(),
        min_net_edge=0.01,
        safety_margin=0.02,
        max_spread=0.05,
    )

    assert decision.status == "REJECTED"
    assert decision.reason_code == "SPREAD_TOO_WIDE"


def test_crypto_barrier_accepts_only_after_margin() -> None:
    decision = CryptoBarrierEngine().evaluate(
        _market(strike=101_000, yes_bid=0.10, yes_ask=0.12),
        spot_price=100_000,
        hourly_closes=_closes(hourly_return=0.004),
        min_net_edge=0.10,
        safety_margin=0.04,
        max_spread=0.05,
    )

    assert decision.action == "BUY_YES"
    assert decision.status == "OPPORTUNITY"
    assert decision.net_edge is not None
    assert decision.net_edge >= 0.10
