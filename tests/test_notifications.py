from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import AppSettings
from app.db.base import Base
from app.db.models import NotificationEvent, Signal, SystemEvent
from app.services.notifications import NotificationService
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
        "bankroll_usd": 10.0,
        "paper_bankroll_usd": 10.0,
        "scan_interval_minutes": 20,
        "min_net_edge": 0.10,
        "max_position_usd": 1.0,
        "max_position_percent": 10.0,
        "max_total_exposure_percent": 25.0,
        "max_daily_loss_percent": 10.0,
        "max_drawdown_percent": 30.0,
        "min_confidence": 55.0,
        "max_spread": 0.08,
        "preferred_horizon_hours": 24,
        "user_timezone": "America/Argentina/Buenos_Aires",
        "alert_email_enabled": True,
        "alert_email_recipient": "santicuervo2210@gmail.com",
        "alert_min_confidence": 70.0,
        "alert_min_net_edge": 0.10,
        "alert_min_model_probability": 0.60,
        "alert_min_profit_usd_per_1": 0.40,
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
        "market_id": "KALSHI:TEST",
        "token_id": "YES",
        "event_id": "EVENT",
        "question": "Will test resolve yes?",
        "city": "Los Angeles",
        "country": "United States",
        "target_date": "2026-08-29",
        "timezone": "America/Los_Angeles",
        "weather_metric": "daily_max",
        "outcome": "85F to 86F",
        "side": "BUY_YES",
        "action": "BUY_YES",
        "status": "OPPORTUNITY",
        "reason_code": "EDGE_OK",
        "reason_es": "ok",
        "reason_en": "ok",
        "market_probability": 0.56,
        "model_probability": 0.72,
        "raw_edge": 0.16,
        "net_edge": 0.11,
        "confidence": 76,
        "executable_price": 0.56,
        "recommended_stake": 1.0,
        "polymarket_url": "https://kalshi.com/markets/test",
    }
    values.update(overrides)
    return Signal(**values)


def test_email_alert_requires_thresholds() -> None:
    session = _session()
    signal = _signal(confidence=55)
    session.add(signal)
    session.flush()

    sent = NotificationService(AppSettings()).maybe_notify_weather_signal(session, signal, _runtime())

    assert not sent
    assert session.query(NotificationEvent).count() == 0


def test_email_alert_records_skip_when_smtp_missing() -> None:
    session = _session()
    signal = _signal()
    session.add(signal)
    session.flush()

    sent = NotificationService(AppSettings()).maybe_notify_weather_signal(session, signal, _runtime())

    event = session.query(NotificationEvent).one()
    assert not sent
    assert event.status == "SKIPPED"
    assert event.error == "SMTP_NOT_CONFIGURED"
    assert session.query(SystemEvent).count() == 1


def test_email_alert_deduplicates_signal(monkeypatch) -> None:
    session = _session()
    signal = _signal()
    session.add(signal)
    session.flush()
    service = NotificationService(AppSettings(smtp_host="smtp.example.com", smtp_username="u", smtp_password="p"))
    sent_messages: list[tuple[str, str, str]] = []
    monkeypatch.setattr(service, "_send_email", lambda recipient, subject, body: sent_messages.append((recipient, subject, body)))

    assert service.maybe_notify_weather_signal(session, signal, _runtime())
    assert not service.maybe_notify_weather_signal(session, signal, _runtime())

    assert len(sent_messages) == 1
    assert session.query(NotificationEvent).count() == 1
    assert session.query(NotificationEvent).one().status == "SENT"
