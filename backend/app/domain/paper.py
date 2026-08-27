from __future__ import annotations

from dataclasses import dataclass

from app.domain.edge import calculate_taker_fee, projected_buy_vwap
from app.domain.types import FeeSchedule, OrderBookSnapshot


@dataclass(frozen=True)
class PaperFill:
    status: str
    fill_price: float | None
    shares: float | None
    fees: float
    reason_code: str


class PaperExecutionEngine:
    def simulate_buy(
        self,
        *,
        orderbook: OrderBookSnapshot,
        requested_price: float,
        stake_usd: float,
        fee_schedule: FeeSchedule,
    ) -> PaperFill:
        if orderbook.best_ask is None or requested_price + 1e-9 < orderbook.best_ask:
            return PaperFill("PENDING", None, None, 0.0, "NOT_MARKETABLE")
        eligible = [level for level in orderbook.asks if level.price <= requested_price]
        if not eligible:
            return PaperFill("PENDING", None, None, 0.0, "NO_EXECUTABLE_ASK")
        synthetic_book = OrderBookSnapshot(
            token_id=orderbook.token_id,
            market=orderbook.market,
            bids=orderbook.bids,
            asks=eligible,
            min_order_size=orderbook.min_order_size,
            tick_size=orderbook.tick_size,
            timestamp_utc=orderbook.timestamp_utc,
            raw=orderbook.raw,
        )
        vwap, _slippage, available = projected_buy_vwap(synthetic_book, stake_usd)
        if vwap is None or available <= 0:
            return PaperFill("PENDING", None, None, 0.0, "NO_LIQUIDITY")
        filled_stake = min(stake_usd, available)
        shares = filled_stake / vwap
        fees = calculate_taker_fee(shares, vwap, fee_schedule)
        status = "FILLED" if available + 1e-9 >= stake_usd else "PARTIALLY_FILLED"
        return PaperFill(status, round(vwap, 6), round(shares, 6), fees, "SIMULATED_FROM_ORDERBOOK")


def calculate_resolved_pnl(*, shares: float, entry_cost: float, entry_fees: float, won: bool, exit_fees: float = 0.0) -> tuple[float, float]:
    payout = shares if won else 0.0
    gross_pnl = payout - entry_cost
    net_pnl = gross_pnl - entry_fees - exit_fees
    return round(gross_pnl, 8), round(net_pnl, 8)
