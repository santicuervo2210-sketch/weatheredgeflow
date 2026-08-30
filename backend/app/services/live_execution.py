from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.config import AppSettings
from app.db.models import CryptoSignal, LiveExecutionAudit, Signal
from app.services.settings_service import RuntimeSettings


SignalSource = Literal["weather", "crypto"]


@dataclass(frozen=True)
class LiveExecutionRequest:
    source: SignalSource
    signal_id: int
    stop_loss_price: float | None = None
    force: bool = False


@dataclass(frozen=True)
class LiveExecutionResult:
    status: str
    reason_code: str
    reason_es: str
    reason_en: str
    audit_id: int
    source: str
    signal_id: int
    venue: str
    instrument: str
    action: str
    limit_price: float | None
    stake_usd: float | None
    stop_loss_price: float | None

    def as_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


class LiveExecutionService:
    """Guarded live execution preflight.

    The service intentionally fails closed unless live execution is explicitly
    enabled through server-side configuration and every risk guard passes.
    """

    def __init__(self, app_settings: AppSettings) -> None:
        self.app_settings = app_settings

    def preflight(self, session: Session, runtime: RuntimeSettings, request: LiveExecutionRequest) -> LiveExecutionResult:
        signal = self._load_signal(session, request)
        if signal is None:
            return self._audit(
                session,
                request=request,
                status="BLOCKED",
                reason_code="SIGNAL_NOT_FOUND",
                reason_es="No existe la señal solicitada.",
                reason_en="Requested signal does not exist.",
            )

        venue, instrument, action, limit_price, stake = self._signal_fields(signal)
        if not runtime.live_execution_enabled or not self.app_settings.live_execution_enabled:
            return self._audit(
                session,
                request=request,
                signal=signal,
                status="BLOCKED",
                reason_code="LIVE_EXECUTION_DISABLED",
                reason_es="Ejecución real deshabilitada. Solo se generan señales.",
                reason_en="Live execution is disabled. The system only generates signals.",
            )
        if runtime.mode != "LIVE_SIGNAL":
            return self._audit(
                session,
                request=request,
                signal=signal,
                status="BLOCKED",
                reason_code="MODE_NOT_LIVE_SIGNAL",
                reason_es="La ejecución real requiere modo LIVE_SIGNAL.",
                reason_en="Live execution requires LIVE_SIGNAL mode.",
            )
        if runtime.kill_switch or runtime.paused:
            return self._audit(
                session,
                request=request,
                signal=signal,
                status="BLOCKED",
                reason_code="CONTROL_DISABLED",
                reason_es="Bot pausado o kill switch activo.",
                reason_en="Bot is paused or kill switch is enabled.",
            )
        if getattr(signal, "status", "") != "OPPORTUNITY" or action == "NO_TRADE":
            return self._audit(
                session,
                request=request,
                signal=signal,
                status="BLOCKED",
                reason_code="SIGNAL_NOT_ACTIONABLE",
                reason_es="La señal no está aprobada como oportunidad accionable.",
                reason_en="Signal is not approved as an actionable opportunity.",
            )
        confidence = float(getattr(signal, "confidence", None) or 0.0)
        if confidence < runtime.live_execution_min_confidence:
            return self._audit(
                session,
                request=request,
                signal=signal,
                status="BLOCKED",
                reason_code="CONFIDENCE_TOO_LOW",
                reason_es="Confidence menor al mínimo de ejecución real.",
                reason_en="Confidence is below the live execution minimum.",
            )
        if stake is None or stake <= 0:
            return self._audit(
                session,
                request=request,
                signal=signal,
                status="BLOCKED",
                reason_code="NO_RECOMMENDED_STAKE",
                reason_es="La señal no tiene stake recomendado positivo.",
                reason_en="Signal has no positive recommended stake.",
            )
        if stake > runtime.live_execution_max_order_usd:
            return self._audit(
                session,
                request=request,
                signal=signal,
                status="BLOCKED",
                reason_code="ORDER_SIZE_LIMIT",
                reason_es="El tamaño supera el máximo permitido para ejecución real.",
                reason_en="Order size exceeds the live execution limit.",
            )
        if runtime.live_execution_stop_loss_required and request.stop_loss_price is None:
            return self._audit(
                session,
                request=request,
                signal=signal,
                status="BLOCKED",
                reason_code="STOP_LOSS_REQUIRED",
                reason_es="Falta stop-loss obligatorio para ejecución real.",
                reason_en="Required stop-loss is missing for live execution.",
            )
        if not self.app_settings.kalshi_api_key_id or not self.app_settings.kalshi_private_key_path:
            return self._audit(
                session,
                request=request,
                signal=signal,
                status="BLOCKED",
                reason_code="API_CREDENTIALS_MISSING",
                reason_es="Faltan credenciales API oficiales configuradas en el servidor.",
                reason_en="Official API credentials are missing on the server.",
            )
        return self._audit(
            session,
            request=request,
            signal=signal,
            status="PREPARED",
            reason_code="READY_FOR_OFFICIAL_EXECUTOR",
            reason_es="Preflight aprobado. El conector de ejecución oficial permanece sin activar en esta sesión.",
            reason_en="Preflight approved. The official execution connector remains inactive in this session.",
        )

    def _load_signal(self, session: Session, request: LiveExecutionRequest) -> Signal | CryptoSignal | None:
        if request.source == "weather":
            return session.get(Signal, request.signal_id)
        return session.get(CryptoSignal, request.signal_id)

    def _signal_fields(self, signal: Signal | CryptoSignal) -> tuple[str, str, str, float | None, float | None]:
        if isinstance(signal, Signal):
            return (
                "KALSHI" if str(signal.market_id).startswith("KALSHI:") else "POLYMARKET",
                signal.outcome or signal.city or signal.market_id,
                signal.action,
                signal.max_recommended_price or signal.executable_price,
                signal.recommended_stake,
            )
        return (
            signal.venue,
            signal.symbol,
            signal.action,
            signal.market_probability,
            signal.recommended_notional,
        )

    def _audit(
        self,
        session: Session,
        *,
        request: LiveExecutionRequest,
        status: str,
        reason_code: str,
        reason_es: str,
        reason_en: str,
        signal: Signal | CryptoSignal | None = None,
    ) -> LiveExecutionResult:
        venue = "UNKNOWN"
        instrument = "UNKNOWN"
        action = "NO_TRADE"
        limit_price = None
        stake = None
        if signal is not None:
            venue, instrument, action, limit_price, stake = self._signal_fields(signal)
        row = LiveExecutionAudit(
            source=request.source,
            signal_id=request.signal_id,
            venue=venue,
            instrument=instrument,
            action=action,
            order_type="LIMIT",
            limit_price=limit_price,
            stake_usd=stake,
            stop_loss_price=request.stop_loss_price,
            status=status,
            reason_code=reason_code,
            reason_es=reason_es,
            reason_en=reason_en,
            raw_json=json.dumps({"request": request.__dict__}, default=str),
        )
        session.add(row)
        session.flush()
        return LiveExecutionResult(
            status=status,
            reason_code=reason_code,
            reason_es=reason_es,
            reason_en=reason_en,
            audit_id=row.id,
            source=request.source,
            signal_id=request.signal_id,
            venue=venue,
            instrument=instrument,
            action=action,
            limit_price=limit_price,
            stake_usd=stake,
            stop_loss_price=request.stop_loss_price,
        )
