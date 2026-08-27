from __future__ import annotations

import math

from app.domain.types import EdgeResult, FeeSchedule, OrderBookSnapshot


class EdgeCalculator:
    def calculate(
        self,
        *,
        model_probability: float,
        orderbook: OrderBookSnapshot,
        fee_schedule: FeeSchedule | None,
        stake_usd: float,
        uncertainty_penalty: float,
        safety_margin: float,
        min_net_edge: float,
    ) -> EdgeResult:
        ask = orderbook.best_ask
        bid = orderbook.best_bid
        spread = orderbook.spread
        if ask is None or bid is None or spread is None:
            return self._reject("NO_ORDERBOOK", model_probability)
        if ask <= 0 or ask >= 1:
            return self._reject("INVALID_PRICE", model_probability)
        if fee_schedule is None or fee_schedule.rate is None:
            return self._reject("FEES_UNKNOWN", model_probability, market_probability=ask, executable_price=ask)

        vwap, slippage, available = projected_buy_vwap(orderbook, stake_usd)
        if vwap is None or available < stake_usd:
            return self._reject("INSUFFICIENT_LIQUIDITY", model_probability, market_probability=ask, executable_price=ask)

        market_probability = vwap
        raw_edge = model_probability - market_probability
        shares = stake_usd / vwap
        estimated_fees = calculate_taker_fee(shares, vwap, fee_schedule)
        fee_probability_cost = estimated_fees / stake_usd if stake_usd > 0 else 1.0
        spread_cost = spread / 2.0
        net_edge = raw_edge - fee_probability_cost - spread_cost - slippage - uncertainty_penalty - safety_margin
        gross_ev = raw_edge * stake_usd
        net_ev = net_edge * stake_usd
        return EdgeResult(
            action="BUY" if net_edge >= min_net_edge else "NO_TRADE",
            raw_edge=raw_edge,
            net_edge=net_edge,
            market_probability=market_probability,
            executable_price=vwap,
            estimated_fees=estimated_fees,
            spread_cost=spread_cost,
            slippage=slippage,
            uncertainty_penalty=uncertainty_penalty,
            safety_margin=safety_margin,
            gross_ev=gross_ev,
            net_ev=net_ev,
            reason_code="EDGE_OK" if net_edge >= min_net_edge else "EDGE_BELOW_THRESHOLD",
        )

    def _reject(
        self,
        reason_code: str,
        model_probability: float,
        *,
        market_probability: float | None = None,
        executable_price: float | None = None,
    ) -> EdgeResult:
        return EdgeResult(
            action="NO_TRADE",
            raw_edge=0.0,
            net_edge=-1.0,
            market_probability=market_probability or 0.0,
            executable_price=executable_price or 0.0,
            estimated_fees=0.0,
            spread_cost=0.0,
            slippage=0.0,
            uncertainty_penalty=0.0,
            safety_margin=0.0,
            gross_ev=0.0,
            net_ev=0.0,
            reason_code=reason_code,
        )


def calculate_taker_fee(shares: float, price: float, fee_schedule: FeeSchedule) -> float:
    if not fee_schedule.enabled or not fee_schedule.rate:
        return 0.0
    component = max(0.0, price * (1.0 - price))
    fee = shares * fee_schedule.rate * (component ** fee_schedule.exponent)
    if fee_schedule.rounding == "ceil_cent":
        return math.ceil((fee - 1e-12) * 100.0) / 100.0 if fee > 0 else 0.0
    return round(fee, 5) if fee >= 0.000005 else 0.0


def projected_buy_vwap(orderbook: OrderBookSnapshot, stake_usd: float) -> tuple[float | None, float, float]:
    remaining = stake_usd
    total_cost = 0.0
    total_shares = 0.0
    best_ask = orderbook.best_ask
    if best_ask is None:
        return None, 1.0, 0.0
    for level in orderbook.asks:
        level_cost = level.price * level.size
        take_cost = min(remaining, level_cost)
        if take_cost <= 0:
            continue
        total_cost += take_cost
        total_shares += take_cost / level.price
        remaining -= take_cost
        if remaining <= 1e-9:
            break
    available = total_cost
    if total_shares <= 0:
        return None, 1.0, available
    vwap = total_cost / total_shares
    slippage = max(0.0, vwap - best_ask)
    return vwap, slippage, available
