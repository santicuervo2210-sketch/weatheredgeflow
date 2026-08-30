from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.db.models import LiveExecutionAudit


ExecutionMode = Literal["PAPER", "SANDBOX", "LIVE_CASH"]
DecisionAction = Literal["comprar", "vender", "mantener", "cerrar_posicion"]


@dataclass(frozen=True)
class OrderExecutionAgentRequest:
    execution_mode: ExecutionMode
    venue: str
    symbol: str
    accion: DecisionAction
    confianza: int
    tamano_posicion: float | str
    stop_loss: float | str
    take_profit: float | str
    current_price: float
    max_order_usd: float
    idempotency_key: str


@dataclass(frozen=True)
class OrderExecutionAgentResult:
    status: str
    reason_code: str
    reason_es: str
    reason_en: str
    audit_id: int
    execution_mode: str
    venue: str
    symbol: str
    action: str
    order_type: str
    limit_price: float | None
    stake_usd: float | None
    stop_loss_price: float | None
    take_profit_price: float | None

    def as_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


class AutonomousOrderExecutionAgent:
    """Executes only non-custodial paper/sandbox orders and audits everything.

    LIVE_CASH intentionally fails closed. A real-money executor must be a
    separate user-run service connected to an official broker/exchange API.
    """

    def run(self, session: Session, request: OrderExecutionAgentRequest) -> OrderExecutionAgentResult:
        existing = self._existing(session, request.idempotency_key)
        if existing is not None:
            return self._from_audit(existing, reason_es="Solicitud repetida: se devolvio la auditoria existente.", reason_en="Repeated request: returned existing audit.")

        if request.accion == "mantener":
            return self._audit(
                session,
                request,
                status="NOOP",
                reason_code="DECISION_HOLD",
                reason_es="Decision mantener: no se crea orden.",
                reason_en="Hold decision: no order is created.",
            )
        if request.current_price <= 0:
            return self._audit(
                session,
                request,
                status="BLOCKED",
                reason_code="INVALID_PRICE",
                reason_es="Precio actual invalido.",
                reason_en="Invalid current price.",
            )
        if request.confianza < 65:
            return self._audit(
                session,
                request,
                status="BLOCKED",
                reason_code="CONFIDENCE_TOO_LOW",
                reason_es="Confianza menor al minimo de ejecucion.",
                reason_en="Confidence below execution minimum.",
            )
        stake = self._float_or_none(request.tamano_posicion)
        if request.accion != "cerrar_posicion" and (stake is None or stake <= 0):
            return self._audit(
                session,
                request,
                status="BLOCKED",
                reason_code="INVALID_POSITION_SIZE",
                reason_es="Tamano de posicion invalido.",
                reason_en="Invalid position size.",
            )
        if stake is not None and stake > request.max_order_usd:
            return self._audit(
                session,
                request,
                status="BLOCKED",
                reason_code="ORDER_SIZE_LIMIT",
                reason_es="La orden supera el maximo permitido.",
                reason_en="Order exceeds the allowed maximum.",
            )
        stop_loss = self._float_or_none(request.stop_loss)
        take_profit = self._float_or_none(request.take_profit)
        if request.accion in {"comprar", "vender"} and (stop_loss is None or take_profit is None):
            return self._audit(
                session,
                request,
                status="BLOCKED",
                reason_code="STOP_LOSS_TAKE_PROFIT_REQUIRED",
                reason_es="Falta stop-loss o take-profit para abrir una posicion.",
                reason_en="Stop-loss or take-profit missing for opening a position.",
            )
        if request.execution_mode == "LIVE_CASH":
            return self._audit(
                session,
                request,
                status="BLOCKED",
                reason_code="LIVE_CASH_DISABLED",
                reason_es="Ejecucion con dinero real bloqueada en este agente. Use solo API oficial en un ejecutor externo propio.",
                reason_en="Real-money execution is blocked in this agent. Use only an official API in your own external executor.",
            )
        status = "EXECUTED_PAPER" if request.execution_mode == "PAPER" else "PREPARED_SANDBOX"
        reason_code = "PAPER_ORDER_CREATED" if request.execution_mode == "PAPER" else "SANDBOX_ORDER_PREPARED"
        reason_es = "Orden paper registrada por el agente." if request.execution_mode == "PAPER" else "Orden sandbox preparada; no usa dinero real."
        reason_en = "Paper order recorded by the agent." if request.execution_mode == "PAPER" else "Sandbox order prepared; no real money is used."
        return self._audit(session, request, status=status, reason_code=reason_code, reason_es=reason_es, reason_en=reason_en)

    def _existing(self, session: Session, idempotency_key: str) -> LiveExecutionAudit | None:
        if not idempotency_key:
            return None
        pattern = f'"idempotency_key": "{idempotency_key}"'
        return (
            session.query(LiveExecutionAudit)
            .filter(LiveExecutionAudit.source == "agent")
            .filter(LiveExecutionAudit.raw_json.contains(pattern))
            .order_by(LiveExecutionAudit.created_at_utc.desc())
            .first()
        )

    def _audit(
        self,
        session: Session,
        request: OrderExecutionAgentRequest,
        *,
        status: str,
        reason_code: str,
        reason_es: str,
        reason_en: str,
    ) -> OrderExecutionAgentResult:
        stake = self._float_or_none(request.tamano_posicion)
        stop_loss = self._float_or_none(request.stop_loss)
        take_profit = self._float_or_none(request.take_profit)
        limit_price = request.current_price if request.accion in {"comprar", "vender"} else None
        row = LiveExecutionAudit(
            source="agent",
            signal_id=None,
            venue=request.venue.upper(),
            instrument=request.symbol.upper(),
            action=request.accion,
            order_type="LIMIT",
            limit_price=limit_price,
            stake_usd=stake,
            stop_loss_price=stop_loss,
            status=status,
            reason_code=reason_code,
            reason_es=reason_es,
            reason_en=reason_en,
            raw_json=json.dumps(
                {
                    "idempotency_key": request.idempotency_key,
                    "execution_mode": request.execution_mode,
                    "take_profit_price": take_profit,
                    "confidence": request.confianza,
                },
                default=str,
            ),
        )
        session.add(row)
        session.flush()
        return OrderExecutionAgentResult(
            status=status,
            reason_code=reason_code,
            reason_es=reason_es,
            reason_en=reason_en,
            audit_id=row.id,
            execution_mode=request.execution_mode,
            venue=request.venue.upper(),
            symbol=request.symbol.upper(),
            action=request.accion,
            order_type="LIMIT",
            limit_price=limit_price,
            stake_usd=stake,
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
        )

    def _from_audit(self, audit: LiveExecutionAudit, *, reason_es: str, reason_en: str) -> OrderExecutionAgentResult:
        raw = json.loads(audit.raw_json or "{}")
        return OrderExecutionAgentResult(
            status=audit.status,
            reason_code="IDEMPOTENT_REPLAY",
            reason_es=reason_es,
            reason_en=reason_en,
            audit_id=audit.id,
            execution_mode=str(raw.get("execution_mode") or "UNKNOWN"),
            venue=audit.venue,
            symbol=audit.instrument,
            action=audit.action,
            order_type=audit.order_type,
            limit_price=audit.limit_price,
            stake_usd=audit.stake_usd,
            stop_loss_price=audit.stop_loss_price,
            take_profit_price=self._float_or_none(raw.get("take_profit_price")),
        )

    def _float_or_none(self, value: float | str | None) -> float | None:
        if value is None or value == "N/A":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
