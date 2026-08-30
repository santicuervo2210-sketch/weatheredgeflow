from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import LiveExecutionAudit
from app.services.order_execution_agent import AutonomousOrderExecutionAgent, OrderExecutionAgentRequest


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _request(**overrides) -> OrderExecutionAgentRequest:
    values = {
        "execution_mode": "PAPER",
        "venue": "BINANCE",
        "symbol": "BTCUSDT",
        "accion": "comprar",
        "confianza": 82,
        "tamano_posicion": 2.0,
        "stop_loss": 104.94,
        "take_profit": 108.12,
        "current_price": 106.0,
        "max_order_usd": 2.0,
        "idempotency_key": "agent-test-1",
    }
    values.update(overrides)
    return OrderExecutionAgentRequest(**values)


def test_order_execution_agent_records_paper_order() -> None:
    session = _session()

    result = AutonomousOrderExecutionAgent().run(session, _request())

    assert result.status == "EXECUTED_PAPER"
    assert result.reason_code == "PAPER_ORDER_CREATED"
    assert result.limit_price == 106.0
    assert result.stake_usd == 2.0
    assert session.query(LiveExecutionAudit).count() == 1


def test_order_execution_agent_blocks_live_cash() -> None:
    session = _session()

    result = AutonomousOrderExecutionAgent().run(
        session,
        _request(execution_mode="LIVE_CASH", idempotency_key="agent-test-live"),
    )

    assert result.status == "BLOCKED"
    assert result.reason_code == "LIVE_CASH_DISABLED"
    assert session.query(LiveExecutionAudit).count() == 1


def test_order_execution_agent_requires_confidence() -> None:
    session = _session()

    result = AutonomousOrderExecutionAgent().run(
        session,
        _request(confianza=40, idempotency_key="agent-test-low-confidence"),
    )

    assert result.status == "BLOCKED"
    assert result.reason_code == "CONFIDENCE_TOO_LOW"


def test_order_execution_agent_requires_stop_loss_and_take_profit() -> None:
    session = _session()

    result = AutonomousOrderExecutionAgent().run(
        session,
        _request(stop_loss="N/A", idempotency_key="agent-test-no-stop"),
    )

    assert result.status == "BLOCKED"
    assert result.reason_code == "STOP_LOSS_TAKE_PROFIT_REQUIRED"


def test_order_execution_agent_idempotency_replays_existing_audit() -> None:
    session = _session()
    agent = AutonomousOrderExecutionAgent()

    first = agent.run(session, _request(idempotency_key="agent-test-replay"))
    second = agent.run(session, _request(idempotency_key="agent-test-replay"))

    assert first.audit_id == second.audit_id
    assert second.reason_code == "IDEMPOTENT_REPLAY"
    assert session.query(LiveExecutionAudit).count() == 1
