from __future__ import annotations

import json
import logging
from typing import Any

from app.clients.binance_public import BinancePublicClient, BinanceMarketSnapshot
from app.clients.kalshi import KalshiClient
from app.config import AppSettings
from app.db.models import CryptoSignal, CryptoSnapshot
from app.db.session import session_scope
from app.domain.crypto_barrier import KalshiCryptoMarket, CryptoBarrierEngine, parse_kalshi_crypto_market
from app.domain.crypto_carry import CryptoCarryEngine, CryptoCarryLimits
from app.services.events import log_event
from app.services.settings_service import SettingsService
from app.utils.time import utc_now


logger = logging.getLogger(__name__)


class CryptoScannerService:
    def __init__(self, app_settings: AppSettings, settings_service: SettingsService) -> None:
        self.app_settings = app_settings
        self.settings_service = settings_service
        self.engine = CryptoCarryEngine()
        self.barrier_engine = CryptoBarrierEngine()

    async def run_once(self) -> dict[str, Any]:
        client = BinancePublicClient(self.app_settings)
        kalshi = KalshiClient(self.app_settings)
        symbols = [symbol.strip().upper() for symbol in self.app_settings.crypto_symbols.split(",") if symbol.strip()]
        scanned = 0
        opportunities = 0
        errors = 0
        try:
            with session_scope() as session:
                log_event(
                    session,
                    message_es="Crypto scanner iniciado",
                    message_en="Crypto scanner started",
                    category="CRYPTO",
                )
            for symbol in symbols:
                try:
                    snapshot = await client.get_snapshot(symbol)
                    created = self._save_decision(snapshot)
                    scanned += 1
                    opportunities += 1 if created else 0
                except Exception as exc:  # noqa: BLE001
                    errors += 1
                    logger.exception("crypto scan failed for %s", symbol)
                    with session_scope() as session:
                        log_event(
                            session,
                            message_es=f"Error crypto {symbol}: {exc}",
                            message_en=f"Crypto error {symbol}: {exc}",
                            category="CRYPTO",
                            level="ERROR",
                        )
            try:
                barrier_result = await self._scan_kalshi_btc_barriers(client, kalshi)
                scanned += barrier_result["markets"]
                opportunities += barrier_result["opportunities"]
                errors += barrier_result["errors"]
            except Exception as exc:  # noqa: BLE001
                errors += 1
                logger.exception("kalshi btc barrier scan failed")
                with session_scope() as session:
                    log_event(
                        session,
                        message_es=f"Error crypto Kalshi BTC: {exc}",
                        message_en=f"Kalshi BTC crypto error: {exc}",
                        category="CRYPTO",
                        level="ERROR",
                    )
            with session_scope() as session:
                log_event(
                    session,
                    message_es=f"Crypto scanner finalizado: {scanned} símbolos, {opportunities} oportunidades",
                    message_en=f"Crypto scanner finished: {scanned} symbols, {opportunities} opportunities",
                    category="CRYPTO",
                    details={"errors": errors},
                )
        finally:
            await client.close()
            await kalshi.close()
        return {"status": "COMPLETED" if errors == 0 else "DEGRADED", "symbols": scanned, "opportunities": opportunities, "errors": errors}

    async def _scan_kalshi_btc_barriers(self, client: BinancePublicClient, kalshi: KalshiClient) -> dict[str, int]:
        series = [item.strip().upper() for item in self.app_settings.kalshi_crypto_series_tickers.split(",") if item.strip()]
        raw_markets = await kalshi.get_markets_by_series(series, limit_per_series=20)
        markets = [market for market in (parse_kalshi_crypto_market(raw) for raw in raw_markets) if market is not None]
        symbols = sorted({market.symbol for market in markets})
        spot_prices: dict[str, float] = {}
        history: dict[tuple[str, str], list[float]] = {}
        for symbol in symbols:
            snapshot = await client.get_snapshot(symbol)
            spot_prices[symbol] = snapshot.spot_mid
            hourly_klines = await client.get_klines(symbol, interval="1h", limit=max(48, self.app_settings.crypto_barrier_vol_window_days * 24))
            history[(symbol, "barrier")] = [row["close"] for row in hourly_klines]
            minute_klines = await client.get_klines(symbol, interval="1m", limit=max(60, self.app_settings.crypto_short_interval_minutes * 12))
            history[(symbol, "directional")] = [row["close"] for row in minute_klines]
        scanned = 0
        opportunities = 0
        errors = 0
        for parsed in markets:
            scanned += 1
            try:
                created = self._save_barrier_decision(
                    parsed,
                    spot_price=spot_prices[parsed.symbol],
                    closes=history[(parsed.symbol, parsed.market_type)],
                )
                opportunities += 1 if created else 0
            except Exception as exc:  # noqa: BLE001
                errors += 1
                logger.info("crypto prediction market skipped %s: %s", parsed.ticker, exc)
        return {"markets": scanned, "opportunities": opportunities, "errors": errors}

    def _save_decision(self, snapshot: BinanceMarketSnapshot) -> bool:
        with session_scope() as session:
            runtime = self.settings_service.get_runtime(session)
            limits = CryptoCarryLimits(
                bankroll=runtime.active_bankroll,
                min_net_daily_edge=self.app_settings.crypto_min_net_daily_edge,
                max_spread=self.app_settings.crypto_max_spread,
                max_basis_risk=self.app_settings.crypto_max_basis_risk,
                min_notional_usd=self.app_settings.crypto_min_notional_usd,
                max_position_usd=runtime.max_position_usd,
                max_position_percent=runtime.max_position_percent,
                spot_fee_rate=self.app_settings.crypto_spot_fee_rate,
                futures_fee_rate=self.app_settings.crypto_futures_fee_rate,
                safety_margin=self.app_settings.crypto_safety_margin,
            )
            decision = self.engine.evaluate(snapshot, limits)
            snapshot_row = CryptoSnapshot(
                timestamp_utc=utc_now(),
                venue="BINANCE",
                symbol=snapshot.symbol,
                spot_bid=snapshot.spot_bid,
                spot_ask=snapshot.spot_ask,
                futures_bid=snapshot.futures_bid,
                futures_ask=snapshot.futures_ask,
                mark_price=snapshot.mark_price,
                index_price=snapshot.index_price,
                funding_rate=snapshot.funding_rate,
                next_funding_time_utc=snapshot.next_funding_time_utc,
                spot_spread=snapshot.spot_spread,
                futures_spread=snapshot.futures_spread,
                basis=snapshot.basis,
                raw_json=json.dumps(snapshot.raw, default=str),
            )
            session.add(snapshot_row)
            session.flush()
            session.add(
                CryptoSignal(
                    timestamp_utc=utc_now(),
                    snapshot_id=snapshot_row.id,
                    venue="BINANCE",
                    symbol=snapshot.symbol,
                    strategy=self.engine.strategy,
                    action=decision.action,
                    status=decision.status,
                    reason_code=decision.reason_code,
                    reason_es=decision.reason_es,
                    reason_en=decision.reason_en,
                    funding_rate=decision.funding_rate,
                    model_probability=None,
                    market_probability=None,
                    raw_edge=None,
                    daily_funding_estimate=decision.daily_funding_estimate,
                    annualized_funding_estimate=decision.annualized_funding_estimate,
                    estimated_costs=decision.estimated_costs,
                    basis_risk=decision.basis_risk,
                    net_daily_edge=decision.net_daily_edge,
                    confidence=decision.confidence,
                    recommended_notional=decision.recommended_notional,
                    max_notional=decision.max_notional,
                    raw_json=json.dumps({"snapshot": snapshot.raw, "decision": decision.__dict__}, default=str),
                )
            )
            log_event(
                session,
                message_es=f"Crypto {snapshot.symbol}: {decision.action} ({decision.reason_code})",
                message_en=f"Crypto {snapshot.symbol}: {decision.action} ({decision.reason_code})",
                category="CRYPTO",
                details={"net_daily_edge": decision.net_daily_edge},
            )
            return decision.status == "OPPORTUNITY"

    def _save_barrier_decision(self, market: KalshiCryptoMarket, *, spot_price: float, closes: list[float]) -> bool:
        min_edge = self.app_settings.crypto_short_min_net_edge if market.market_type == "directional" else self.app_settings.crypto_barrier_min_net_edge
        safety_margin = self.app_settings.crypto_short_safety_margin if market.market_type == "directional" else self.app_settings.crypto_barrier_safety_margin
        max_spread = self.app_settings.crypto_short_max_spread if market.market_type == "directional" else self.app_settings.crypto_barrier_max_spread
        decision = self.barrier_engine.evaluate(
            market,
            spot_price=spot_price,
            hourly_closes=closes,
            min_net_edge=min_edge,
            safety_margin=safety_margin,
            max_spread=max_spread,
        )
        with session_scope() as session:
            session.add(
                CryptoSignal(
                    timestamp_utc=utc_now(),
                    snapshot_id=None,
                    venue="KALSHI",
                    symbol=decision.symbol,
                    strategy=self.barrier_engine.strategy,
                    action=decision.action,
                    status=decision.status,
                    reason_code=decision.reason_code,
                    reason_es=decision.reason_es,
                    reason_en=decision.reason_en,
                    funding_rate=None,
                    model_probability=decision.model_probability,
                    market_probability=decision.market_probability,
                    raw_edge=decision.raw_edge,
                    daily_funding_estimate=None,
                    annualized_funding_estimate=None,
                    estimated_costs=None,
                    basis_risk=None,
                    net_daily_edge=decision.net_edge,
                    confidence=decision.confidence,
                    recommended_notional=0.0,
                    max_notional=0.0,
                    raw_json=json.dumps({"market": market.raw, "decision": decision.__dict__}, default=str),
                )
            )
            log_event(
                session,
                message_es=f"Kalshi BTC {market.ticker}: {decision.action} ({decision.reason_code})",
                message_en=f"Kalshi BTC {market.ticker}: {decision.action} ({decision.reason_code})",
                category="CRYPTO",
                details={"model_probability": decision.model_probability, "market_probability": decision.market_probability},
            )
            return decision.status == "OPPORTUNITY"
