from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.api.schemas import ControlUpdate, ModeUpdate, ScanResponse, SettingsUpdate
from app.clients.kalshi import KalshiClient
from app.clients.polymarket import PolymarketClient
from app.clients.weather import OpenMeteoProvider, TheWeatherCompanyKalshiProvider
from app.config import get_settings
from app.db.models import (
    BankrollSnapshot,
    PaperOrder,
    PaperPosition,
    Scan,
    Signal,
    SystemEvent,
)
from app.db.session import session_scope
from app.services.events import log_event
from app.services.portfolio import PortfolioService
from app.services.settings_service import SettingsService
from app.utils.time import iso_utc


router = APIRouter()


@router.get("/health")
async def api_health(request: Request) -> dict[str, Any]:
    return await build_health(request)


@router.get("/dashboard")
async def dashboard(request: Request) -> dict[str, Any]:
    settings_service: SettingsService = request.app.state.settings_service
    scheduler = request.app.state.scheduler
    portfolio = PortfolioService()
    with session_scope() as session:
        runtime = settings_service.get_runtime(session)
        settings = settings_service.get_all(session)
        latest_scan = session.query(Scan).order_by(Scan.started_at_utc.desc()).first()
        signals = session.query(Signal).order_by(Signal.created_at_utc.desc()).limit(100).all()
        positions = session.query(PaperPosition).order_by(PaperPosition.opened_at_utc.desc()).limit(100).all()
        orders = session.query(PaperOrder).order_by(PaperOrder.order_timestamp_utc.desc()).limit(100).all()
        events = session.query(SystemEvent).order_by(SystemEvent.timestamp_utc.desc()).limit(120).all()
        snapshots = session.query(BankrollSnapshot).order_by(BankrollSnapshot.timestamp_utc.asc()).limit(500).all()
        metrics = portfolio.metrics(session, runtime)
        analytics = build_analytics(session)
        return {
            "settings": settings,
            "runtime": runtime.__dict__,
            "system": system_state(latest_scan, scheduler.status()),
            "latest_scan": scan_dict(latest_scan) if latest_scan else None,
            "metrics": metrics,
            "signals": [signal_dict(s) for s in signals],
            "positions": [position_dict(p) for p in positions],
            "orders": [order_dict(o) for o in orders],
            "activity": [event_dict(e) for e in events],
            "bankroll_chart": [snapshot_dict(s) for s in snapshots],
            "analytics": analytics,
        }


@router.get("/signals/{signal_id}")
async def signal_detail(signal_id: int) -> dict[str, Any]:
    with session_scope() as session:
        signal = session.get(Signal, signal_id)
        if signal is None:
            raise HTTPException(status_code=404, detail="Signal not found")
        return signal_dict(signal, details=True)


@router.get("/settings")
async def get_settings_endpoint(request: Request) -> dict[str, Any]:
    settings_service: SettingsService = request.app.state.settings_service
    with session_scope() as session:
        return settings_service.get_all(session)


@router.patch("/settings")
async def update_settings(request: Request, payload: SettingsUpdate) -> dict[str, Any]:
    settings_service: SettingsService = request.app.state.settings_service
    scheduler = request.app.state.scheduler
    try:
        with session_scope() as session:
            updated = settings_service.update(session, payload.updates, confirmed=payload.confirmed)
            log_event(
                session,
                message_es="Settings actualizados",
                message_en="Settings updated",
                category="SETTINGS",
                details={"keys": list(payload.updates)},
            )
        if "scan_interval_minutes" in payload.updates:
            scheduler.reschedule()
        return updated
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/mode")
async def set_mode(request: Request, payload: ModeUpdate) -> dict[str, Any]:
    settings_service: SettingsService = request.app.state.settings_service
    with session_scope() as session:
        updated = settings_service.update(session, {"mode": payload.mode}, confirmed=payload.confirmed)
        log_event(
            session,
            message_es=f"Modo cambiado a {payload.mode}",
            message_en=f"Mode changed to {payload.mode}",
            category="SETTINGS",
        )
        return updated


@router.patch("/control")
async def control(request: Request, payload: ControlUpdate) -> dict[str, Any]:
    settings_service: SettingsService = request.app.state.settings_service
    updates = {}
    if payload.paused is not None:
        updates["paused"] = payload.paused
    if payload.kill_switch is not None:
        updates["kill_switch"] = payload.kill_switch
    with session_scope() as session:
        updated = settings_service.update(session, updates, confirmed=True)
        if "paused" in updates:
            log_event(
                session,
                message_es="Bot pausado" if updates["paused"] else "Bot reanudado",
                message_en="Bot paused" if updates["paused"] else "Bot resumed",
                category="CONTROL",
            )
        if "kill_switch" in updates:
            log_event(
                session,
                message_es="Kill switch activado" if updates["kill_switch"] else "Kill switch desactivado",
                message_en="Kill switch enabled" if updates["kill_switch"] else "Kill switch disabled",
                category="CONTROL",
                level="WARNING" if updates["kill_switch"] else "INFO",
            )
        return updated


@router.post("/scan", response_model=ScanResponse)
async def run_scan(request: Request) -> dict[str, Any]:
    scanner = request.app.state.scanner
    return await scanner.run_once()


@router.get("/activity")
async def activity(limit: int = 200) -> dict[str, Any]:
    with session_scope() as session:
        events = session.query(SystemEvent).order_by(SystemEvent.timestamp_utc.desc()).limit(min(limit, 500)).all()
        return {"items": [event_dict(e) for e in events]}


async def build_health(request: Request) -> dict[str, Any]:
    settings = get_settings()
    scheduler = request.app.state.scheduler
    db_ok = False
    db_error = None
    try:
        with session_scope() as session:
            session.execute(text("SELECT 1")).scalar()
            db_ok = True
    except Exception as exc:  # noqa: BLE001
        db_error = str(exc)
    venue_name = settings.venue
    venue = KalshiClient(settings) if venue_name == "KALSHI" else PolymarketClient(settings)
    weather = OpenMeteoProvider(settings)
    twc = TheWeatherCompanyKalshiProvider(settings)
    try:
        venue_health = await venue.health()
    finally:
        await venue.close()
    try:
        weather_health = await weather.health()
    finally:
        await weather.close()
    try:
        twc_health = await twc.health()
    finally:
        await twc.close()
    scheduler_health = scheduler.status()
    venue_ok = bool(venue_health.get("ok") if venue_name == "KALSHI" else venue_health.get("gamma"))
    twc_ok = bool(twc_health.get("ok")) if venue_name == "KALSHI" else True
    ok = db_ok and bool(scheduler_health["running"]) and venue_ok and weather_health.get("ok") and twc_ok
    degraded = db_ok and bool(scheduler_health["running"]) and weather_health.get("ok")
    return {
        "status": "ONLINE" if ok else ("DEGRADED" if degraded else "OFFLINE"),
        "application": True,
        "database": {"ok": db_ok, "error": db_error},
        "scheduler": scheduler_health,
        "venue": {"name": venue_name, "health": venue_health},
        "polymarket": venue_health if venue_name == "POLYMARKET" else {"skipped": True},
        "kalshi": venue_health if venue_name == "KALSHI" else {"skipped": True},
        "weather": weather_health,
        "weather_company_kalshi": twc_health,
    }


def system_state(latest_scan: Scan | None, scheduler_status: dict[str, Any]) -> dict[str, Any]:
    if not scheduler_status.get("running"):
        status = "OFFLINE"
    elif latest_scan and latest_scan.status == "DEGRADED":
        status = "DEGRADED"
    else:
        status = "SYSTEM ONLINE"
    return {
        "status": status,
        "scheduler": scheduler_status,
    }


def scan_dict(scan: Scan | None) -> dict[str, Any] | None:
    if not scan:
        return None
    return {
        "id": scan.id,
        "started_at_utc": iso_utc(scan.started_at_utc),
        "finished_at_utc": iso_utc(scan.finished_at_utc),
        "status": scan.status,
        "mode": scan.mode,
        "markets_found": scan.markets_found,
        "weather_markets_found": scan.weather_markets_found,
        "supported_markets": scan.supported_markets,
        "opportunities_found": scan.opportunities_found,
        "errors_count": scan.errors_count,
        "duration_ms": scan.duration_ms,
        "next_scan_at_utc": iso_utc(scan.next_scan_at_utc),
        "summary_es": scan.summary_es,
        "summary_en": scan.summary_en,
    }


def signal_dict(signal: Signal, *, details: bool = False) -> dict[str, Any]:
    base = {
        "id": signal.id,
        "scan_id": signal.scan_id,
        "market_id": signal.market_id,
        "token_id": signal.token_id,
        "event_id": signal.event_id,
        "question": signal.question,
        "city": signal.city,
        "country": signal.country,
        "target_date": signal.target_date,
        "timezone": signal.timezone,
        "weather_metric": signal.weather_metric,
        "outcome": signal.outcome,
        "side": signal.side,
        "action": signal.action,
        "status": signal.status,
        "reason_code": signal.reason_code,
        "reason_es": signal.reason_es,
        "reason_en": signal.reason_en,
        "market_probability": signal.market_probability,
        "model_probability": signal.model_probability,
        "raw_edge": signal.raw_edge,
        "net_edge": signal.net_edge,
        "confidence": signal.confidence,
        "executable_price": signal.executable_price,
        "max_recommended_price": signal.max_recommended_price,
        "best_bid": signal.best_bid,
        "best_ask": signal.best_ask,
        "spread": signal.spread,
        "liquidity_usd": signal.liquidity_usd,
        "fee_rate": signal.fee_rate,
        "estimated_fees": signal.estimated_fees,
        "spread_cost": signal.spread_cost,
        "slippage": signal.slippage,
        "uncertainty_penalty": signal.uncertainty_penalty,
        "safety_margin": signal.safety_margin,
        "gross_ev": signal.gross_ev,
        "net_ev": signal.net_ev,
        "recommended_stake": signal.recommended_stake,
        "maximum_allowed_stake": signal.maximum_allowed_stake,
        "resolution_source": signal.resolution_source,
        "resolution_station": signal.resolution_station,
        "resolution_rules": signal.resolution_rules,
        "polymarket_url": signal.polymarket_url,
        "created_at_utc": iso_utc(signal.created_at_utc),
    }
    if details:
        base.update(
            {
                "distribution": loads(signal.distribution_json, {}),
                "forecasts": loads(signal.forecasts_json, []),
                "observation": loads(signal.observation_json, {}),
                "risks": loads(signal.risks_json, {}),
                "data_freshness": loads(signal.data_freshness_json, {}),
            }
        )
    return base


def position_dict(position: PaperPosition) -> dict[str, Any]:
    return {
        "id": position.id,
        "order_id": position.order_id,
        "market_id": position.market_id,
        "token_id": position.token_id,
        "event_id": position.event_id,
        "outcome": position.outcome,
        "entry_price": position.entry_price,
        "shares": position.shares,
        "stake_usd": position.stake_usd,
        "fees": position.fees,
        "status": position.status,
        "opened_at_utc": iso_utc(position.opened_at_utc),
        "resolved_at_utc": iso_utc(position.resolved_at_utc),
        "gross_pnl": position.gross_pnl,
        "net_pnl": position.net_pnl,
    }


def order_dict(order: PaperOrder) -> dict[str, Any]:
    return {
        "id": order.id,
        "signal_id": order.signal_id,
        "order_timestamp_utc": iso_utc(order.order_timestamp_utc),
        "market_id": order.market_id,
        "token_id": order.token_id,
        "side": order.side,
        "requested_price": order.requested_price,
        "simulated_fill_price": order.simulated_fill_price,
        "stake_usd": order.stake_usd,
        "shares": order.shares,
        "fees": order.fees,
        "status": order.status,
        "pnl": order.pnl,
    }


def event_dict(event: SystemEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "timestamp_utc": iso_utc(event.timestamp_utc),
        "level": event.level,
        "category": event.category,
        "message_es": event.message_es,
        "message_en": event.message_en,
        "details": loads(event.details_json, {}),
    }


def snapshot_dict(snapshot: BankrollSnapshot) -> dict[str, Any]:
    return {
        "timestamp_utc": iso_utc(snapshot.timestamp_utc),
        "bankroll": snapshot.bankroll,
        "cash": snapshot.cash,
        "open_exposure": snapshot.open_exposure,
        "realized_pnl": snapshot.realized_pnl,
        "unrealized_pnl": snapshot.unrealized_pnl,
        "roi": snapshot.roi,
        "drawdown": snapshot.drawdown,
    }


def build_analytics(session: Session) -> dict[str, Any]:
    total_signals = session.query(Signal).count()
    paper_trades = session.query(PaperOrder).count()
    wins = session.query(PaperPosition).filter(PaperPosition.status == "WIN").count()
    losses = session.query(PaperPosition).filter(PaperPosition.status == "LOSS").count()
    avg_edge = float(session.query(func.coalesce(func.avg(Signal.net_edge), 0.0)).scalar() or 0.0)
    avg_return = float(session.query(func.coalesce(func.avg(PaperPosition.net_pnl / PaperPosition.stake_usd), 0.0)).scalar() or 0.0)
    by_city = [
        {"city": city or "Unknown", "signals": count}
        for city, count in session.query(Signal.city, func.count(Signal.id)).group_by(Signal.city).all()
    ]
    confidence_buckets = bucket_counts(session, "confidence")
    edge_buckets = bucket_counts(session, "net_edge")
    gross_profit = float(
        session.query(func.coalesce(func.sum(PaperPosition.net_pnl), 0.0)).filter(PaperPosition.net_pnl > 0).scalar() or 0.0
    )
    gross_loss = abs(
        float(session.query(func.coalesce(func.sum(PaperPosition.net_pnl), 0.0)).filter(PaperPosition.net_pnl < 0).scalar() or 0.0)
    )
    return {
        "total_signals": total_signals,
        "paper_trades": paper_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": wins / (wins + losses) if wins + losses else 0.0,
        "roi": 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss else 0.0,
        "average_edge": avg_edge,
        "average_realized_return": avg_return,
        "max_drawdown": 0.0,
        "brier_score": None,
        "calibration": calibration(session),
        "results_by_city": by_city,
        "results_by_time_to_resolution": [],
        "results_by_edge_bucket": edge_buckets,
        "results_by_confidence": confidence_buckets,
        "results_by_forecast_model": [],
    }


def bucket_counts(session: Session, column_name: str) -> list[dict[str, Any]]:
    column = getattr(Signal, column_name)
    rows = session.query(column).filter(column.is_not(None)).all()
    buckets: dict[str, int] = {}
    for (value,) in rows:
        if value is None:
            continue
        if column_name == "confidence":
            label = f"{int(value // 10) * 10}-{int(value // 10) * 10 + 9}"
        else:
            pct = value * 100
            label = f"{int(pct // 5) * 5}-{int(pct // 5) * 5 + 4}pp"
        buckets[label] = buckets.get(label, 0) + 1
    return [{"bucket": key, "count": value} for key, value in sorted(buckets.items())]


def calibration(session: Session) -> list[dict[str, Any]]:
    rows = session.query(Signal.model_probability).filter(Signal.model_probability.is_not(None)).all()
    buckets: dict[str, dict[str, Any]] = {}
    for (probability,) in rows:
        bucket_start = int((probability or 0) * 10) * 10
        label = f"{bucket_start}-{bucket_start + 10}%"
        item = buckets.setdefault(label, {"bucket": label, "predicted_avg": 0.0, "count": 0, "observed_rate": None})
        item["predicted_avg"] += probability
        item["count"] += 1
    for item in buckets.values():
        item["predicted_avg"] = item["predicted_avg"] / item["count"] if item["count"] else 0.0
    return list(buckets.values())


def loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback
