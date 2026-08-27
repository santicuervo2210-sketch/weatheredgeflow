from __future__ import annotations

from dataclasses import dataclass

from app.domain.edge import projected_buy_vwap
from app.domain.types import OrderBookSnapshot


@dataclass(frozen=True)
class LiquidityDecision:
    ok: bool
    reason_code: str
    reason_es: str
    reason_en: str
    liquidity_usd: float
    projected_price: float | None
    slippage: float


class LiquidityFilter:
    def assess(self, orderbook: OrderBookSnapshot, *, stake_usd: float, max_spread: float) -> LiquidityDecision:
        if orderbook.best_bid is None or orderbook.best_ask is None:
            return self._reject("NO_ORDERBOOK", "Libro vacío.", "Empty order book.")
        spread = orderbook.spread
        if spread is None:
            return self._reject("NO_ORDERBOOK", "No hay bid/ask suficiente.", "Missing bid/ask.")
        if spread > max_spread:
            return self._reject("SPREAD_TOO_WIDE", "Spread demasiado amplio.", "Spread is too wide.")
        if orderbook.min_order_size is not None and stake_usd + 1e-9 < orderbook.min_order_size:
            return self._reject(
                "BELOW_MIN_ORDER",
                "Stake menor al mínimo del mercado.",
                "Stake is below the market minimum order size.",
            )
        vwap, slippage, available = projected_buy_vwap(orderbook, stake_usd)
        if vwap is None or available + 1e-9 < stake_usd:
            return self._reject("INSUFFICIENT_LIQUIDITY", "Liquidez insuficiente al precio ejecutable.", "Insufficient executable liquidity.")
        return LiquidityDecision(
            ok=True,
            reason_code="LIQUID",
            reason_es="Liquidez suficiente.",
            reason_en="Sufficient liquidity.",
            liquidity_usd=available,
            projected_price=vwap,
            slippage=slippage,
        )

    def _reject(self, code: str, es: str, en: str) -> LiquidityDecision:
        return LiquidityDecision(False, code, es, en, 0.0, None, 0.0)

