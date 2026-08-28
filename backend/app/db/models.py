from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.utils.time import utc_now


class Market(Base):
    __tablename__ = "markets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str | None] = mapped_column(String(128), index=True)
    market_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    condition_id: Mapped[str | None] = mapped_column(String(256), index=True)
    question: Mapped[str] = mapped_column(Text)
    slug: Mapped[str | None] = mapped_column(String(512))
    category: Mapped[str | None] = mapped_column(String(128))
    polymarket_url: Mapped[str | None] = mapped_column(String(1024))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    closed: Mapped[bool] = mapped_column(Boolean, default=False)
    end_date_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    outcomes: Mapped[list["MarketOutcome"]] = relationship(back_populates="market")


class MarketOutcome(Base):
    __tablename__ = "market_outcomes"
    __table_args__ = (UniqueConstraint("market_id", "token_id", name="uq_market_outcome_token"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_ref_id: Mapped[int] = mapped_column(ForeignKey("markets.id", ondelete="CASCADE"))
    market_id: Mapped[str] = mapped_column(String(128), index=True)
    token_id: Mapped[str] = mapped_column(String(256), index=True)
    outcome: Mapped[str] = mapped_column(String(256))
    side: Mapped[str] = mapped_column(String(32), default="YES")
    lower_bound: Mapped[float | None] = mapped_column(Float)
    upper_bound: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    market: Mapped[Market] = relationship(back_populates="outcomes")


class WeatherForecast(Base):
    __tablename__ = "weather_forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_id: Mapped[int | None] = mapped_column(ForeignKey("scans.id", ondelete="SET NULL"))
    market_id: Mapped[str] = mapped_column(String(128), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    model_name: Mapped[str] = mapped_column(String(128))
    city: Mapped[str] = mapped_column(String(128))
    country: Mapped[str | None] = mapped_column(String(128))
    timezone: Mapped[str] = mapped_column(String(128))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    weather_metric: Mapped[str] = mapped_column(String(32))
    target_date: Mapped[str] = mapped_column(String(32))
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16))
    issued_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    raw_json: Mapped[str] = mapped_column(Text)


class WeatherObservation(Base):
    __tablename__ = "weather_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_id: Mapped[int | None] = mapped_column(ForeignKey("scans.id", ondelete="SET NULL"))
    market_id: Mapped[str] = mapped_column(String(128), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    station: Mapped[str | None] = mapped_column(String(128))
    observed_max: Mapped[float | None] = mapped_column(Float)
    observed_min: Mapped[float | None] = mapped_column(Float)
    current_temperature: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16))
    observed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    raw_json: Mapped[str] = mapped_column(Text)


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    finished_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="RUNNING")
    mode: Mapped[str] = mapped_column(String(32), default="PAPER")
    markets_found: Mapped[int] = mapped_column(Integer, default=0)
    weather_markets_found: Mapped[int] = mapped_column(Integer, default=0)
    supported_markets: Mapped[int] = mapped_column(Integer, default=0)
    opportunities_found: Mapped[int] = mapped_column(Integer, default=0)
    errors_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    next_scan_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary_es: Mapped[str | None] = mapped_column(Text)
    summary_en: Mapped[str | None] = mapped_column(Text)


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_id: Mapped[int | None] = mapped_column(ForeignKey("scans.id", ondelete="SET NULL"), index=True)
    market_id: Mapped[str] = mapped_column(String(128), index=True)
    token_id: Mapped[str | None] = mapped_column(String(256), index=True)
    event_id: Mapped[str | None] = mapped_column(String(128), index=True)
    question: Mapped[str] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(128))
    country: Mapped[str | None] = mapped_column(String(128))
    target_date: Mapped[str | None] = mapped_column(String(32))
    timezone: Mapped[str | None] = mapped_column(String(128))
    weather_metric: Mapped[str | None] = mapped_column(String(32))
    outcome: Mapped[str | None] = mapped_column(String(256))
    side: Mapped[str] = mapped_column(String(32), default="BUY_YES")
    action: Mapped[str] = mapped_column(String(32), default="NO_TRADE")
    status: Mapped[str] = mapped_column(String(32), default="REJECTED")
    reason_code: Mapped[str] = mapped_column(String(128))
    reason_es: Mapped[str] = mapped_column(Text)
    reason_en: Mapped[str] = mapped_column(Text)
    market_probability: Mapped[float | None] = mapped_column(Float)
    model_probability: Mapped[float | None] = mapped_column(Float)
    raw_edge: Mapped[float | None] = mapped_column(Float)
    net_edge: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    executable_price: Mapped[float | None] = mapped_column(Float)
    max_recommended_price: Mapped[float | None] = mapped_column(Float)
    best_bid: Mapped[float | None] = mapped_column(Float)
    best_ask: Mapped[float | None] = mapped_column(Float)
    spread: Mapped[float | None] = mapped_column(Float)
    liquidity_usd: Mapped[float | None] = mapped_column(Float)
    fee_rate: Mapped[float | None] = mapped_column(Float)
    estimated_fees: Mapped[float | None] = mapped_column(Float)
    spread_cost: Mapped[float | None] = mapped_column(Float)
    slippage: Mapped[float | None] = mapped_column(Float)
    uncertainty_penalty: Mapped[float | None] = mapped_column(Float)
    safety_margin: Mapped[float | None] = mapped_column(Float)
    gross_ev: Mapped[float | None] = mapped_column(Float)
    net_ev: Mapped[float | None] = mapped_column(Float)
    recommended_stake: Mapped[float | None] = mapped_column(Float)
    maximum_allowed_stake: Mapped[float | None] = mapped_column(Float)
    resolution_source: Mapped[str | None] = mapped_column(String(512))
    resolution_station: Mapped[str | None] = mapped_column(String(256))
    resolution_rules: Mapped[str | None] = mapped_column(Text)
    polymarket_url: Mapped[str | None] = mapped_column(String(1024))
    distribution_json: Mapped[str | None] = mapped_column(Text)
    forecasts_json: Mapped[str | None] = mapped_column(Text)
    observation_json: Mapped[str | None] = mapped_column(Text)
    risks_json: Mapped[str | None] = mapped_column(Text)
    data_freshness_json: Mapped[str | None] = mapped_column(Text)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class CryptoSnapshot(Base):
    __tablename__ = "crypto_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    venue: Mapped[str] = mapped_column(String(64), default="BINANCE")
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    spot_bid: Mapped[float | None] = mapped_column(Float)
    spot_ask: Mapped[float | None] = mapped_column(Float)
    futures_bid: Mapped[float | None] = mapped_column(Float)
    futures_ask: Mapped[float | None] = mapped_column(Float)
    mark_price: Mapped[float | None] = mapped_column(Float)
    index_price: Mapped[float | None] = mapped_column(Float)
    funding_rate: Mapped[float | None] = mapped_column(Float)
    next_funding_time_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    spot_spread: Mapped[float | None] = mapped_column(Float)
    futures_spread: Mapped[float | None] = mapped_column(Float)
    basis: Mapped[float | None] = mapped_column(Float)
    raw_json: Mapped[str] = mapped_column(Text)


class CryptoSignal(Base):
    __tablename__ = "crypto_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("crypto_snapshots.id", ondelete="SET NULL"), index=True)
    venue: Mapped[str] = mapped_column(String(64), default="BINANCE")
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    strategy: Mapped[str] = mapped_column(String(64), default="SPOT_PERP_CARRY")
    action: Mapped[str] = mapped_column(String(64), default="NO_TRADE")
    status: Mapped[str] = mapped_column(String(32), default="REJECTED")
    reason_code: Mapped[str] = mapped_column(String(128))
    reason_es: Mapped[str] = mapped_column(Text)
    reason_en: Mapped[str] = mapped_column(Text)
    funding_rate: Mapped[float | None] = mapped_column(Float)
    daily_funding_estimate: Mapped[float | None] = mapped_column(Float)
    annualized_funding_estimate: Mapped[float | None] = mapped_column(Float)
    estimated_costs: Mapped[float | None] = mapped_column(Float)
    basis_risk: Mapped[float | None] = mapped_column(Float)
    net_daily_edge: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    recommended_notional: Mapped[float | None] = mapped_column(Float)
    max_notional: Mapped[float | None] = mapped_column(Float)
    raw_json: Mapped[str] = mapped_column(Text)


class PaperOrder(Base):
    __tablename__ = "paper_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.id", ondelete="CASCADE"), index=True)
    order_timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    market_id: Mapped[str] = mapped_column(String(128), index=True)
    token_id: Mapped[str] = mapped_column(String(256), index=True)
    side: Mapped[str] = mapped_column(String(32))
    requested_price: Mapped[float] = mapped_column(Float)
    simulated_fill_price: Mapped[float | None] = mapped_column(Float)
    stake_usd: Mapped[float] = mapped_column(Float)
    shares: Mapped[float | None] = mapped_column(Float)
    fees: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    pnl: Mapped[float] = mapped_column(Float, default=0)


class PaperPosition(Base):
    __tablename__ = "paper_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("paper_orders.id", ondelete="CASCADE"), index=True)
    market_id: Mapped[str] = mapped_column(String(128), index=True)
    token_id: Mapped[str] = mapped_column(String(256), index=True)
    event_id: Mapped[str | None] = mapped_column(String(128), index=True)
    outcome: Mapped[str] = mapped_column(String(256))
    entry_price: Mapped[float] = mapped_column(Float)
    shares: Mapped[float] = mapped_column(Float)
    stake_usd: Mapped[float] = mapped_column(Float)
    fees: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(32), default="OPEN")
    opened_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gross_pnl: Mapped[float] = mapped_column(Float, default=0)
    net_pnl: Mapped[float] = mapped_column(Float, default=0)


class Resolution(Base):
    __tablename__ = "resolutions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_id: Mapped[str] = mapped_column(String(128), index=True)
    winning_token_id: Mapped[str | None] = mapped_column(String(256))
    winning_outcome: Mapped[str | None] = mapped_column(String(256))
    resolved_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    source: Mapped[str | None] = mapped_column(String(512))
    raw_json: Mapped[str] = mapped_column(Text)


class BankrollSnapshot(Base):
    __tablename__ = "bankroll_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    mode: Mapped[str] = mapped_column(String(32), default="PAPER")
    bankroll: Mapped[float] = mapped_column(Float)
    cash: Mapped[float] = mapped_column(Float)
    open_exposure: Mapped[float] = mapped_column(Float)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0)
    roi: Mapped[float] = mapped_column(Float, default=0)
    drawdown: Mapped[float] = mapped_column(Float, default=0)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SystemEvent(Base):
    __tablename__ = "system_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    level: Mapped[str] = mapped_column(String(16), default="INFO")
    category: Mapped[str] = mapped_column(String(64), default="SYSTEM")
    message_es: Mapped[str] = mapped_column(Text)
    message_en: Mapped[str] = mapped_column(Text)
    details_json: Mapped[str | None] = mapped_column(Text)
