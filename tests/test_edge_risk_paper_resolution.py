from __future__ import annotations

from datetime import UTC, datetime

from app.domain.edge import EdgeCalculator, calculate_taker_fee
from app.domain.liquidity import LiquidityFilter
from app.domain.paper import PaperExecutionEngine, calculate_resolved_pnl
from app.domain.resolution import ResolutionEngine
from app.domain.risk import RiskLimits, RiskManager
from app.domain.types import FeeSchedule, OrderBookLevel, OrderBookSnapshot


def _book() -> OrderBookSnapshot:
    return OrderBookSnapshot(
        token_id="yes-token",
        market="0xabc",
        bids=[OrderBookLevel(0.41, 50), OrderBookLevel(0.40, 100)],
        asks=[OrderBookLevel(0.42, 10), OrderBookLevel(0.43, 100)],
        min_order_size=1,
        tick_size=0.01,
        timestamp_utc=datetime(2026, 8, 27, tzinfo=UTC),
        raw={},
    )


def test_fee_formula_matches_fee_curve_shape() -> None:
    fee = calculate_taker_fee(100, 0.3, FeeSchedule(True, 0.05, 1, True, 0.25, "test"))
    assert fee == 1.05
    symmetric = calculate_taker_fee(100, 0.7, FeeSchedule(True, 0.05, 1, True, 0.25, "test"))
    assert symmetric == fee


def test_edge_rejects_small_apparent_edge_after_costs() -> None:
    result = EdgeCalculator().calculate(
        model_probability=0.52,
        orderbook=_book(),
        fee_schedule=FeeSchedule(True, 0.05, 1, True, 0.25, "test"),
        stake_usd=1,
        uncertainty_penalty=0.03,
        safety_margin=0.03,
        min_net_edge=0.10,
    )
    assert result.action == "NO_TRADE"
    assert result.reason_code == "EDGE_BELOW_THRESHOLD"


def test_liquidity_filter_rejects_wide_spread() -> None:
    wide = OrderBookSnapshot("t", "m", [OrderBookLevel(0.2, 10)], [OrderBookLevel(0.4, 10)], 1, 0.01, datetime.now(UTC), {})
    decision = LiquidityFilter().assess(wide, stake_usd=1, max_spread=0.08)
    assert not decision.ok
    assert decision.reason_code == "SPREAD_TOO_WIDE"


def test_risk_limits_cap_position_size() -> None:
    decision = RiskManager().assess(
        limits=RiskLimits(10, 10, 1, 25, 10, 30, 55),
        requested_stake=3,
        open_exposure=0,
        grouped_event_exposure=0,
        daily_pnl=0,
        drawdown_percent=0,
        net_edge=0.2,
        confidence=80,
    )
    assert decision.approved
    assert decision.maximum_allowed_stake == 1
    assert decision.recommended_stake <= 1


def test_risk_daily_stop_blocks_new_signal() -> None:
    decision = RiskManager().assess(
        limits=RiskLimits(10, 10, 1, 25, 10, 30, 55),
        requested_stake=1,
        open_exposure=0,
        grouped_event_exposure=0,
        daily_pnl=-1.01,
        drawdown_percent=0,
        net_edge=0.2,
        confidence=90,
    )
    assert not decision.approved
    assert decision.reason_code == "DAILY_LOSS_LIMIT"


def test_paper_fill_uses_executable_orderbook_price() -> None:
    fill = PaperExecutionEngine().simulate_buy(
        orderbook=_book(),
        requested_price=0.42,
        stake_usd=1,
        fee_schedule=FeeSchedule(True, 0.05, 1, True, 0.25, "test"),
    )
    assert fill.status == "FILLED"
    assert fill.fill_price == 0.42
    assert fill.shares


def test_resolved_pnl_win_and_loss() -> None:
    gross, net = calculate_resolved_pnl(shares=2, entry_cost=0.8, entry_fees=0.02, won=True)
    assert gross == 1.2
    assert net == 1.18
    gross_loss, net_loss = calculate_resolved_pnl(shares=2, entry_cost=0.8, entry_fees=0.02, won=False)
    assert gross_loss == -0.8
    assert net_loss == -0.82


def test_resolution_extracts_winner_from_prices() -> None:
    winner_token, winner_label = ResolutionEngine().extract_winner(
        {
            "closed": True,
            "outcomes": '["18°C","19°C"]',
            "clobTokenIds": '["t18","t19"]',
            "outcomePrices": '["0","1"]',
        }
    )
    assert winner_token == "t19"
    assert winner_label == "19°C"

