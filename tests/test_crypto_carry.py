from __future__ import annotations

from app.clients.binance_public import parse_binance_snapshot
from app.domain.crypto_carry import CryptoCarryEngine, CryptoCarryLimits


def _snapshot(funding_rate: str = "0.00010000"):
    return parse_binance_snapshot(
        "BTCUSDT",
        {"symbol": "BTCUSDT", "bidPrice": "100000.00", "bidQty": "1.2", "askPrice": "100010.00", "askQty": "0.8"},
        {"symbol": "BTCUSDT", "bidPrice": "100020.00", "bidQty": "4.0", "askPrice": "100030.00", "askQty": "3.5"},
        {
            "symbol": "BTCUSDT",
            "markPrice": "100025.00",
            "indexPrice": "100000.00",
            "lastFundingRate": funding_rate,
            "nextFundingTime": 1790000000000,
        },
    )


def _limits(bankroll: float = 1000) -> CryptoCarryLimits:
    return CryptoCarryLimits(
        bankroll=bankroll,
        min_net_daily_edge=0.001,
        max_spread=0.001,
        max_basis_risk=0.005,
        min_notional_usd=25,
        max_position_usd=100,
        max_position_percent=10,
        spot_fee_rate=0.001,
        futures_fee_rate=0.0005,
        safety_margin=0.001,
    )


def test_binance_snapshot_parses_spreads_basis_and_funding() -> None:
    snapshot = _snapshot()
    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.spot_spread > 0
    assert snapshot.futures_spread > 0
    assert snapshot.basis == 0.00025
    assert snapshot.next_funding_time_utc is not None


def test_crypto_carry_rejects_tiny_bankroll() -> None:
    decision = CryptoCarryEngine().evaluate(_snapshot("0.01000000"), _limits(bankroll=10))
    assert decision.action == "NO_TRADE"
    assert decision.reason_code == "BELOW_MIN_NOTIONAL"


def test_crypto_carry_rejects_when_costs_exceed_funding() -> None:
    decision = CryptoCarryEngine().evaluate(_snapshot("0.00010000"), _limits())
    assert decision.action == "NO_TRADE"
    assert decision.reason_code == "COSTS_EXCEED_EDGE"


def test_crypto_carry_accepts_only_after_costs_and_margin() -> None:
    decision = CryptoCarryEngine().evaluate(_snapshot("0.00300000"), _limits())
    assert decision.action == "BUY_SPOT_SHORT_PERP"
    assert decision.status == "OPPORTUNITY"
    assert decision.net_daily_edge > 0.001
