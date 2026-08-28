from __future__ import annotations

import json
import logging
from typing import Any

from app.clients.binance_public import BinancePublicClient, BinanceMarketSnapshot
from app.config import AppSettings
from app.db.models import CryptoSignal, CryptoSnapshot
from app.db.session import session_scope
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

    async def run_once(self) -> dict[str, Any]:
        client = BinancePublicClient(self.app_settings)
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
        return {"status": "COMPLETED" if errors == 0 else "DEGRADED", "symbols": scanned, "opportunities": opportunities, "errors": errors}

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
