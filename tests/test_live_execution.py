from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import AppSettings
from app.db.base import Base
from app.db.models import LiveExecutionAudit, Signal
from app.services.live_execution import LiveExecutionRequest, LiveExecutionService
from app.services.settings_service import RuntimeSettings


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _runtime(**overrides) -> RuntimeSettings:
    values = {
        "language": "es",
        "venue": "KALSHI",
        "mode": "LIVE_SIGNAL",
        "bankroll_usd": 100.0,
        "paper_bankroll_usd": 100.0,
        "scan_interval_minutes": 3,
        "min_net_edge": 0.10,
        "max_position_usd": 2.0,
        "max_position_percent": 2.0,
        "max_total_exposure_percent": 10.0,
        "max_daily_loss_percent": 5.0,
        "max_drawdown_percent": 20.0,
        "min_confidence": 60.0,
        "max_spread": 0.08,
        "preferred_horizon_hours": 24,
        "user_timezone": "America/Argentina/Buenos_Aires",
        "alert_email_enabled": False,
        "alert_email_recipient": "",
        "alert_min_confidence": 60.0,
        "alert_min_net_edge": 0.10,
        "alert_min_model_probability": 0.55,
        "alert_min_profit_usd_per_1": 0.10,
        "live_execution_enabled": False,
        "live_execution_provider": "DISABLED",
        "live_execution_max_order_usd": 2.0,
        "live_execution_stop_loss_required": True,
        "live_execution_min_confidence": 65.0,
        "paused": False,
        "kill_switch": False,
    }
    values.update(overrides)
    return RuntimeSettings(**values)


def _signal(**overrides) -> Signal:
    values = {
        "scan_id": None,
        "market_id": "KALSHI:KXTEST",
        "token_id": "KALSHI:KXTEST:YES",
        "event_id": "KALSHI:TEST",
        "question": "Will test resolve yes?",
        "city": "Austin",
        "country": "US",
        "target_date": "2026-08-30",
        "timezone": "America/Chicago",
        "weather_metric": "daily_max",
        "outcome": "99F to 100F",
        "side": "BUY_YES",
        "action": "BUY_YES",
        "status": "OPPORTUNITY",
        "reason_code": "EDGE_OK",
        "reason_es": "ok",
        "reason_en": "ok",
        "market_probability": 0.42,
        "model_probability": 0.62,
        "raw_edge": 0.20,
        "net_edge": 0.12,
        "confidence": 76.0,
        "executable_price": 0.42,
        "max_recommended_price": 0.42,
        "recommended_stake": 1.0,
        "polymarket_url": "https://kalshi.com/markets/test",
    }
    values.update(overrides)
    return Signal(**values)


def test_live_preflight_blocks_when_disabled_and_audits() -> None:
    session = _session()
    signal = _signal()
    session.add(signal)
    session.commit()

    result = LiveExecutionService(AppSettings(live_execution_enabled=False)).preflight(
        session,
        _runtime(live_execution_enabled=False),
        LiveExecutionRequest(source="weather", signal_id=signal.id, stop_loss_price=0.25),
    )

    assert result.status == "BLOCKED"
    assert result.reason_code == "LIVE_EXECUTION_DISABLED"
    assert session.query(LiveExecutionAudit).count() == 1


def test_live_preflight_requires_stop_loss_before_credentials() -> None:
    session = _session()
    signal = _signal()
    session.add(signal)
    session.commit()

    result = LiveExecutionService(AppSettings(live_execution_enabled=True)).preflight(
        session,
        _runtime(live_execution_enabled=True),
        LiveExecutionRequest(source="weather", signal_id=signal.id),
    )

    assert result.status == "BLOCKED"
    assert result.reason_code == "STOP_LOSS_REQUIRED"


def test_live_preflight_blocks_missing_api_credentials() -> None:
    session = _session()
    signal = _signal()
    session.add(signal)
    session.commit()

    result = LiveExecutionService(AppSettings(live_execution_enabled=True)).preflight(
        session,
        _runtime(live_execution_enabled=True),
        LiveExecutionRequest(source="weather", signal_id=signal.id, stop_loss_price=0.25),
    )

    assert result.status == "BLOCKED"
    assert result.reason_code == "API_CREDENTIALS_MISSING"
