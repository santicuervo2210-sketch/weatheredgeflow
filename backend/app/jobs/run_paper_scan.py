from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from sqlalchemy import func

from app.config import get_settings
from app.db.migrations import run_migrations
from app.db.models import PaperOrder, PaperPosition, Scan, Signal
from app.db.session import engine, session_scope
from app.services.portfolio import PortfolioService
from app.services.scanner import ScannerService
from app.services.settings_service import SettingsService
from app.utils.logging import configure_logging


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    run_migrations(engine)
    settings_service = SettingsService(settings)
    with session_scope() as session:
        settings_service.initialize(session)

    scanner = ScannerService(settings, settings_service)
    result = await scanner.run_once()
    summary = build_summary(settings_service, result)
    write_reports(summary)
    print(json.dumps(summary, indent=2, default=str))


def build_summary(settings_service: SettingsService, scan_result: dict[str, Any]) -> dict[str, Any]:
    portfolio = PortfolioService()
    with session_scope() as session:
        runtime = settings_service.get_runtime(session)
        latest_scan = session.query(Scan).order_by(Scan.started_at_utc.desc()).first()
        opportunity_count = (
            session.query(func.count(Signal.id))
            .filter(Signal.scan_id == latest_scan.id, Signal.status == "OPPORTUNITY")
            .scalar()
            if latest_scan
            else 0
        )
        rejected_count = (
            session.query(func.count(Signal.id))
            .filter(Signal.scan_id == latest_scan.id, Signal.status.in_(("REJECTED", "DISCARDED")))
            .scalar()
            if latest_scan
            else 0
        )
        recent_signals = (
            session.query(Signal)
            .filter(Signal.scan_id == latest_scan.id)
            .order_by(Signal.net_edge.desc().nullslast(), Signal.created_at_utc.desc())
            .limit(20)
            .all()
            if latest_scan
            else []
        )
        metrics = portfolio.metrics(session, runtime)
        return {
            "scan_result": scan_result,
            "mode": runtime.mode,
            "venue": runtime.venue,
            "latest_scan": {
                "id": latest_scan.id if latest_scan else None,
                "status": latest_scan.status if latest_scan else None,
                "markets_found": latest_scan.markets_found if latest_scan else 0,
                "supported_markets": latest_scan.supported_markets if latest_scan else 0,
                "opportunities_found": latest_scan.opportunities_found if latest_scan else 0,
                "errors_count": latest_scan.errors_count if latest_scan else 0,
                "duration_ms": latest_scan.duration_ms if latest_scan else None,
                "started_at_utc": latest_scan.started_at_utc.isoformat() if latest_scan else None,
                "finished_at_utc": latest_scan.finished_at_utc.isoformat() if latest_scan and latest_scan.finished_at_utc else None,
            },
            "counts": {
                "opportunity_signals": int(opportunity_count or 0),
                "rejected_signals": int(rejected_count or 0),
                "paper_orders": session.query(PaperOrder).count(),
                "open_positions": session.query(PaperPosition).filter(PaperPosition.status == "OPEN").count(),
            },
            "metrics": metrics,
            "top_signals": [
                {
                    "market": signal.question,
                    "city": signal.city,
                    "outcome": signal.outcome,
                    "action": signal.action,
                    "status": signal.status,
                    "reason": signal.reason_code,
                    "model_probability": signal.model_probability,
                    "market_probability": signal.market_probability,
                    "net_edge": signal.net_edge,
                    "confidence": signal.confidence,
                    "stake": signal.recommended_stake,
                    "url": signal.polymarket_url,
                }
                for signal in recent_signals
            ],
        }


def write_reports(summary: dict[str, Any]) -> None:
    reports = Path("reports")
    reports.mkdir(exist_ok=True)
    (reports / "latest_scan.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    latest = summary["latest_scan"]
    counts = summary["counts"]
    lines = [
        "# WeatherEdgeflow GitHub PAPER Scan",
        "",
        f"- Status: {latest['status']}",
        f"- Venue: {summary['venue']}",
        f"- Mode: {summary['mode']}",
        f"- Markets found: {latest['markets_found']}",
        f"- Supported markets: {latest['supported_markets']}",
        f"- Opportunities: {latest['opportunities_found']}",
        f"- Errors: {latest['errors_count']}",
        f"- Paper orders total: {counts['paper_orders']}",
        f"- Open PAPER positions: {counts['open_positions']}",
        "",
        "## Top Signals",
        "",
    ]
    for signal in summary["top_signals"][:10]:
        lines.append(
            "- "
            f"{signal['status']} | {signal['action']} | edge={_pct(signal['net_edge'])} | "
            f"confidence={_num(signal['confidence'])} | {signal['city']} | {signal['outcome']} | {signal['reason']}"
        )
    (reports / "latest_scan.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _pct(value: Any) -> str:
    return "-" if value is None else f"{float(value) * 100:.1f}%"


def _num(value: Any) -> str:
    return "-" if value is None else f"{float(value):.1f}"


if __name__ == "__main__":
    asyncio.run(main())
