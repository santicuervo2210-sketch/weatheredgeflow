from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import CryptoSignal, Signal
from app.services.market_radar import MarketRadarService
from app.services.settings_service import RuntimeSettings


def _runtime() -> RuntimeSettings:
    return RuntimeSettings(
        language="es",
        venue="KALSHI",
        mode="PAPER",
        bankroll_usd=100.0,
        paper_bankroll_usd=100.0,
        scan_interval_minutes=20,
        min_net_edge=0.10,
        max_position_usd=2.0,
        max_position_percent=2.0,
        max_total_exposure_percent=15.0,
        max_daily_loss_percent=5.0,
        max_drawdown_percent=20.0,
        min_confidence=55.0,
        max_spread=0.08,
        preferred_horizon_hours=24,
        user_timezone="America/Argentina/Buenos_Aires",
        alert_email_enabled=False,
        alert_email_recipient="",
        alert_min_confidence=70.0,
        alert_min_net_edge=0.10,
        alert_min_model_probability=0.60,
        alert_min_profit_usd_per_1=0.40,
        paused=False,
        kill_switch=False,
    )


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_market_radar_prefers_actionable_weather_signal() -> None:
    session = _session()
    session.add(
        Signal(
            scan_id=None,
            market_id="KALSHI:KXHIGHNY-26AUG28-B84.5",
            token_id="YES",
            event_id="KALSHI:KXHIGHNY",
            question="Will NYC be 84-85?",
            city="New York City",
            outcome="84F to 85F",
            action="BUY_YES",
            status="OPPORTUNITY",
            reason_code="EDGE_CONFIRMED",
            reason_es="Edge confirmado.",
            reason_en="Edge confirmed.",
            model_probability=0.74,
            market_probability=0.55,
            raw_edge=0.19,
            net_edge=0.13,
            confidence=82.0,
            recommended_stake=2.0,
            polymarket_url="https://kalshi.com/markets/kxhighny",
        )
    )
    session.add(
        CryptoSignal(
            timestamp_utc=datetime.now(tz=UTC),
            snapshot_id=None,
            venue="KALSHI",
            symbol="BTCUSDT",
            strategy="KALSHI_CRYPTO_PRICE",
            action="NO_TRADE",
            status="REJECTED",
            reason_code="EDGE_BELOW_THRESHOLD",
            reason_es="Edge insuficiente.",
            reason_en="Edge below threshold.",
            model_probability=0.60,
            market_probability=0.55,
            raw_edge=0.05,
            net_daily_edge=0.05,
            confidence=65.0,
            recommended_notional=0.0,
            raw_json="{}",
        )
    )
    session.commit()

    radar = MarketRadarService().build(session, _runtime())

    assert radar["status"] == "OPPORTUNITY"
    assert radar["best"]["source"] == "weather"
    assert radar["best"]["action"] == "BUY_YES"
    assert radar["actionable_count"] == 1


def test_market_radar_fails_closed_with_watchlist_only() -> None:
    session = _session()
    session.add(
        CryptoSignal(
            timestamp_utc=datetime.now(tz=UTC),
            snapshot_id=None,
            venue="KALSHI",
            symbol="BTCUSDT",
            strategy="KALSHI_CRYPTO_PRICE",
            action="NO_TRADE",
            status="REJECTED",
            reason_code="EDGE_BELOW_THRESHOLD",
            reason_es="Edge insuficiente.",
            reason_en="Edge below threshold.",
            model_probability=0.62,
            market_probability=0.54,
            raw_edge=0.08,
            net_daily_edge=0.06,
            confidence=61.0,
            recommended_notional=0.0,
            raw_json="{}",
        )
    )
    session.commit()

    radar = MarketRadarService().build(session, _runtime())

    assert radar["status"] == "NO_TRADE"
    assert radar["best"] is None
    assert radar["best_watchlist"]["instrument"] == "BTCUSDT"
    assert radar["summary_es"].startswith("Radar multi-mercado: NO TRADE")
