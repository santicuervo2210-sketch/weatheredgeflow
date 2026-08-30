from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import pstdev
from typing import Any

from app.utils.time import parse_datetime, utc_now


@dataclass(frozen=True)
class KalshiCryptoMarket:
    ticker: str
    event_ticker: str
    title: str
    symbol: str
    market_type: str
    direction: str
    strike: float | None
    close_time_utc: datetime
    start_time_utc: datetime | None
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
    strike: float | None
    days_to_expiry: float


class CryptoBarrierEngine:
    strategy = "KALSHI_CRYPTO_PRICE"

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
        if market.market_type == "directional":
            probability = short_direction_probability(
                spot_price=spot_price,
                minute_closes=hourly_closes,
                close_time_utc=market.close_time_utc,
                start_time_utc=market.start_time_utc,
            )
            confidence = max(18.0, min(58.0, 48.0 - abs(probability - 0.5) * 10.0))
        else:
            if market.strike is None:
                return self._reject(market, "MISSING_STRIKE", "El mercado no tiene strike numérico interpretable.", "The market has no parseable numeric strike.", 0.0, None, None, None, 0.0, realized_vol, spot_price, days)
            probability = barrier_touch_probability(
                spot_price=spot_price,
                barrier=market.strike,
                annualized_vol=realized_vol,
                years=days / 365.0,
                direction=market.direction,
            )
            confidence = max(20.0, min(72.0, 64.0 - abs(probability - 0.5) * 18.0))
        side, executable, side_bid, side_spread, raw_edge = best_side(probability, market)
        if executable is None or side_bid is None or executable <= 0 or executable >= 1 or side_spread is None:
            return self._reject(market, "NO_MARKET_PRICE", "Precio Kalshi no ejecutable.", "Kalshi executable price is unavailable.", probability, None, None, None, confidence, realized_vol, spot_price, days)
        if side_spread > max_spread:
            return self._reject(market, "SPREAD_TOO_WIDE", "Spread demasiado amplio para una predicción crypto conservadora.", "Spread is too wide for a conservative crypto prediction.", probability, executable, raw_edge, None, confidence, realized_vol, spot_price, days)
        net_edge = raw_edge - side_spread / 2.0 - safety_margin
        if net_edge < min_net_edge:
            return self._reject(market, "EDGE_BELOW_THRESHOLD", "Edge neto insuficiente después de spread y margen de seguridad.", "Net edge is too small after spread and safety margin.", probability, executable, raw_edge, net_edge, confidence, realized_vol, spot_price, days)
        return CryptoBarrierDecision(
            symbol=market.symbol,
            ticker=market.ticker,
            action=side,
            status="OPPORTUNITY",
            reason_code="CRYPTO_EDGE_OK",
            reason_es="Modelo crypto detecta probabilidad superior al precio de Kalshi después de spread y margen.",
            reason_en="Crypto model detects probability above Kalshi price after spread and safety margin.",
            model_probability=probability,
            market_probability=executable,
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
            symbol=market.symbol,
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
    return parse_kalshi_crypto_market(raw)


def parse_kalshi_crypto_market(raw: dict[str, Any]) -> KalshiCryptoMarket | None:
    title = str(raw.get("title") or "")
    lowered = f" {title} ".lower()
    symbol = _symbol_from_title(title)
    if symbol is None:
        return None
    close_time = parse_datetime(str(raw.get("close_time") or raw.get("expected_expiration_time") or ""))
    if close_time is None:
        return None
    if close_time.tzinfo is None:
        close_time = close_time.replace(tzinfo=UTC)
    close_time = close_time.astimezone(UTC)
    if close_time <= utc_now():
        return None
    if " price up in next 15 mins" in lowered:
        return KalshiCryptoMarket(
            ticker=str(raw.get("ticker") or ""),
            event_ticker=str(raw.get("event_ticker") or ""),
            title=title,
            symbol=symbol,
            market_type="directional",
            direction="up",
            strike=None,
            close_time_utc=close_time,
            start_time_utc=close_time - timedelta(minutes=15),
            yes_bid=_float_or_none(raw.get("yes_bid_dollars")),
            yes_ask=_float_or_none(raw.get("yes_ask_dollars")),
            no_bid=_float_or_none(raw.get("no_bid_dollars")),
            no_ask=_float_or_none(raw.get("no_ask_dollars")),
            raw=raw,
        )
    direction = "above" if " above " in lowered else "below" if " below " in lowered else None
    if direction is None:
        return None
    match = re.search(r"\$([0-9,]+(?:\.[0-9]+)?)", title)
    if not match:
        return None
    return KalshiCryptoMarket(
        ticker=str(raw.get("ticker") or ""),
        event_ticker=str(raw.get("event_ticker") or ""),
        title=title,
        symbol=symbol,
        market_type="barrier",
        direction=direction,
        strike=float(match.group(1).replace(",", "")),
        close_time_utc=close_time,
        start_time_utc=None,
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


def short_direction_probability(
    *,
    spot_price: float,
    minute_closes: list[float],
    close_time_utc: datetime,
    start_time_utc: datetime | None,
) -> float:
    now = utc_now()
    if spot_price <= 0 or len(minute_closes) < 30 or close_time_utc <= now:
        return 0.0
    if start_time_utc is None or now < start_time_utc:
        start_price = minute_closes[-1]
    else:
        index_from_end = min(len(minute_closes), int((now - start_time_utc).total_seconds() // 60) + 1)
        start_price = minute_closes[-index_from_end]
    returns = [math.log(minute_closes[index] / minute_closes[index - 1]) for index in range(1, len(minute_closes)) if minute_closes[index] > 0 and minute_closes[index - 1] > 0]
    if len(returns) < 30:
        raise ValueError("Not enough minute returns")
    sigma = max(0.0001, pstdev(returns))
    minutes_left = max(1.0, (close_time_utc - now).total_seconds() / 60.0)
    sigma_t = sigma * math.sqrt(minutes_left)
    distance = math.log(spot_price / start_price)
    return max(0.0, min(1.0, _normal_cdf(distance / sigma_t)))


def best_side(probability_yes: float, market: KalshiCryptoMarket) -> tuple[str, float | None, float | None, float | None, float]:
    yes_spread = None if market.yes_ask is None or market.yes_bid is None else max(0.0, market.yes_ask - market.yes_bid)
    no_spread = None if market.no_ask is None or market.no_bid is None else max(0.0, market.no_ask - market.no_bid)
    yes_edge = -math.inf if market.yes_ask is None else probability_yes - market.yes_ask
    no_probability = 1.0 - probability_yes
    no_edge = -math.inf if market.no_ask is None else no_probability - market.no_ask
    if no_edge > yes_edge:
        return "BUY_NO", market.no_ask, market.no_bid, no_spread, no_edge
    return "BUY_YES", market.yes_ask, market.yes_bid, yes_spread, yes_edge


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


def _symbol_from_title(title: str) -> str | None:
    lowered = title.lower()
    if "bitcoin cash" in lowered:
        return "BCHUSDT"
    if "bitcoin" in lowered:
        return "BTCUSDT"
    if "ethereum" in lowered or "eth price" in lowered:
        return "ETHUSDT"
    if "solana" in lowered or "sol price" in lowered:
        return "SOLUSDT"
    if "xrp" in lowered:
        return "XRPUSDT"
    if "dogecoin" in lowered or "doge price" in lowered:
        return "DOGEUSDT"
    if "litecoin" in lowered:
        return "LTCUSDT"
    return None


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
