from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import pstdev
from typing import Any

from app.utils.time import parse_datetime, utc_now


@dataclass(frozen=True)
class KalshiCryptoMarket:
    ticker: str
    event_ticker: str
    title: str
    direction: str
    strike: float
    close_time_utc: datetime
    yes_bid: float | None
    yes_ask: float | None
    no_bid: float | None
    no_ask: float | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class CryptoBarrierDecision:
    symbol: str
    ticker: str
    action: str
    status: str
    reason_code: str
    reason_es: str
    reason_en: str
    model_probability: float
    market_probability: float | None
    raw_edge: float | None
    net_edge: float | None
    confidence: float
    realized_vol: float
    spot_price: float
    strike: float
    days_to_expiry: float


class CryptoBarrierEngine:
    strategy = "KALSHI_BTC_BARRIER"

    def evaluate(
        self,
        market: KalshiCryptoMarket,
        *,
        spot_price: float,
        hourly_closes: list[float],
        min_net_edge: float,
        safety_margin: float,
        max_spread: float,
    ) -> CryptoBarrierDecision:
        realized_vol = annualized_realized_vol(hourly_closes)
        days = max(0.0, (market.close_time_utc - utc_now()).total_seconds() / 86400.0)
        probability = barrier_touch_probability(
            spot_price=spot_price,
            barrier=market.strike,
            annualized_vol=realized_vol,
            years=days / 365.0,
            direction=market.direction,
        )
        confidence = max(20.0, min(72.0, 64.0 - abs(probability - 0.5) * 18.0))
        ask = market.yes_ask
        bid = market.yes_bid
        spread = None if ask is None or bid is None else max(0.0, ask - bid)
        if ask is None or bid is None or ask <= 0 or ask >= 1 or spread is None:
            return self._reject(market, "NO_MARKET_PRICE", "Precio Kalshi no ejecutable.", "Kalshi executable price is unavailable.", probability, None, None, None, confidence, realized_vol, spot_price, days)
        if spread > max_spread:
            return self._reject(market, "SPREAD_TOO_WIDE", "Spread demasiado amplio para una predicción crypto conservadora.", "Spread is too wide for a conservative crypto prediction.", probability, ask, probability - ask, None, confidence, realized_vol, spot_price, days)
        raw_edge = probability - ask
        net_edge = raw_edge - spread / 2.0 - safety_margin
        if net_edge < min_net_edge:
            return self._reject(market, "EDGE_BELOW_THRESHOLD", "Edge neto insuficiente después de spread y margen de seguridad.", "Net edge is too small after spread and safety margin.", probability, ask, raw_edge, net_edge, confidence, realized_vol, spot_price, days)
        return CryptoBarrierDecision(
            symbol="BTCUSDT",
            ticker=market.ticker,
            action="BUY_YES",
            status="OPPORTUNITY",
            reason_code="BARRIER_EDGE_OK",
            reason_es="Modelo de barrera detecta probabilidad superior al precio de Kalshi después de spread y margen.",
            reason_en="Barrier model detects probability above Kalshi price after spread and safety margin.",
            model_probability=probability,
            market_probability=ask,
            raw_edge=raw_edge,
            net_edge=net_edge,
            confidence=confidence,
            realized_vol=realized_vol,
            spot_price=spot_price,
            strike=market.strike,
            days_to_expiry=days,
        )

    def _reject(
        self,
        market: KalshiCryptoMarket,
        code: str,
        reason_es: str,
        reason_en: str,
        probability: float,
        market_probability: float | None,
        raw_edge: float | None,
        net_edge: float | None,
        confidence: float,
        realized_vol: float,
        spot_price: float,
        days: float,
    ) -> CryptoBarrierDecision:
        return CryptoBarrierDecision(
            symbol="BTCUSDT",
            ticker=market.ticker,
            action="NO_TRADE",
            status="REJECTED",
            reason_code=code,
            reason_es=reason_es,
            reason_en=reason_en,
            model_probability=probability,
            market_probability=market_probability,
            raw_edge=raw_edge,
            net_edge=net_edge,
            confidence=confidence,
            realized_vol=realized_vol,
            spot_price=spot_price,
            strike=market.strike,
            days_to_expiry=days,
        )


def parse_kalshi_btc_market(raw: dict[str, Any]) -> KalshiCryptoMarket | None:
    title = str(raw.get("title") or "")
    if "Bitcoin" not in title:
        return None
    direction = "above" if " above " in f" {title} ".lower() else "below" if " below " in f" {title} ".lower() else None
    if direction is None:
        return None
    match = re.search(r"\$([0-9,]+(?:\.[0-9]+)?)", title)
    if not match:
        return None
    close_time = parse_datetime(str(raw.get("close_time") or raw.get("expected_expiration_time") or ""))
    if close_time is None:
        return None
    if close_time.tzinfo is None:
        close_time = close_time.replace(tzinfo=UTC)
    return KalshiCryptoMarket(
        ticker=str(raw.get("ticker") or ""),
        event_ticker=str(raw.get("event_ticker") or ""),
        title=title,
        direction=direction,
        strike=float(match.group(1).replace(",", "")),
        close_time_utc=close_time.astimezone(UTC),
        yes_bid=_float_or_none(raw.get("yes_bid_dollars")),
        yes_ask=_float_or_none(raw.get("yes_ask_dollars")),
        no_bid=_float_or_none(raw.get("no_bid_dollars")),
        no_ask=_float_or_none(raw.get("no_ask_dollars")),
        raw=raw,
    )


def annualized_realized_vol(closes: list[float]) -> float:
    returns = [math.log(closes[index] / closes[index - 1]) for index in range(1, len(closes)) if closes[index] > 0 and closes[index - 1] > 0]
    if len(returns) < 24:
        raise ValueError("Not enough returns for volatility")
    return max(0.01, pstdev(returns) * math.sqrt(24 * 365))


def barrier_touch_probability(
    *,
    spot_price: float,
    barrier: float,
    annualized_vol: float,
    years: float,
    direction: str,
) -> float:
    if spot_price <= 0 or barrier <= 0 or annualized_vol <= 0 or years <= 0:
        return 0.0
    sigma_t = annualized_vol * math.sqrt(years)
    if direction == "above":
        if spot_price >= barrier:
            return 1.0
        distance = math.log(barrier / spot_price)
        return max(0.0, min(1.0, 2.0 * (1.0 - _normal_cdf(distance / sigma_t))))
    if direction == "below":
        if spot_price <= barrier:
            return 1.0
        distance = math.log(barrier / spot_price)
        return max(0.0, min(1.0, 2.0 * _normal_cdf(distance / sigma_t)))
    return 0.0


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
