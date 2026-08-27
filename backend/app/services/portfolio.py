from __future__ import annotations

from datetime import UTC, datetime, time
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import BankrollSnapshot, PaperPosition
from app.services.settings_service import RuntimeSettings
from app.utils.time import utc_now


class PortfolioService:
    def metrics(self, session: Session, settings: RuntimeSettings) -> dict[str, Any]:
        initial = settings.paper_bankroll_usd
        positions = session.query(PaperPosition).all()
        open_positions = [p for p in positions if p.status == "OPEN"]
        closed_positions = [p for p in positions if p.status != "OPEN"]
        open_exposure = sum(p.stake_usd + p.fees for p in open_positions)
        realized_pnl = sum(p.net_pnl for p in closed_positions)
        unrealized_pnl = 0.0
        bankroll = initial + realized_pnl + unrealized_pnl
        cash = bankroll - open_exposure
        roi = (bankroll - initial) / initial if initial else 0.0
        wins = sum(1 for p in closed_positions if p.net_pnl > 0)
        losses = sum(1 for p in closed_positions if p.net_pnl < 0)
        gross_profit = sum(p.net_pnl for p in closed_positions if p.net_pnl > 0)
        gross_loss = abs(sum(p.net_pnl for p in closed_positions if p.net_pnl < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)
        max_drawdown = self.max_drawdown(session, initial)
        return {
            "initial_bankroll": round(initial, 4),
            "bankroll": round(bankroll, 4),
            "cash": round(cash, 4),
            "open_exposure": round(open_exposure, 4),
            "realized_pnl": round(realized_pnl, 4),
            "unrealized_pnl": round(unrealized_pnl, 4),
            "today_pnl": round(self.daily_pnl(session), 4),
            "roi": round(roi, 6),
            "max_drawdown": round(max_drawdown, 6),
            "win_rate": round(wins / (wins + losses), 4) if wins + losses else 0.0,
            "profit_factor": round(profit_factor, 4),
            "number_of_trades": len(closed_positions),
        }

    def snapshot(self, session: Session, settings: RuntimeSettings) -> BankrollSnapshot:
        metrics = self.metrics(session, settings)
        row = BankrollSnapshot(
            timestamp_utc=utc_now(),
            mode=settings.mode,
            bankroll=metrics["bankroll"],
            cash=metrics["cash"],
            open_exposure=metrics["open_exposure"],
            realized_pnl=metrics["realized_pnl"],
            unrealized_pnl=metrics["unrealized_pnl"],
            roi=metrics["roi"],
            drawdown=metrics["max_drawdown"],
        )
        session.add(row)
        session.flush()
        return row

    def daily_pnl(self, session: Session) -> float:
        start = datetime.combine(utc_now().date(), time.min, tzinfo=UTC)
        return float(
            session.query(func.coalesce(func.sum(PaperPosition.net_pnl), 0.0))
            .filter(PaperPosition.resolved_at_utc >= start)
            .scalar()
            or 0.0
        )

    def grouped_open_exposure(self, session: Session) -> float:
        rows = (
            session.query(PaperPosition.event_id, func.sum(PaperPosition.stake_usd + PaperPosition.fees))
            .filter(PaperPosition.status == "OPEN")
            .group_by(PaperPosition.event_id)
            .all()
        )
        return float(sum(row[1] or 0.0 for row in rows))

    def event_open_exposure(self, session: Session, event_id: str | None) -> float:
        query = session.query(func.coalesce(func.sum(PaperPosition.stake_usd + PaperPosition.fees), 0.0)).filter(
            PaperPosition.status == "OPEN"
        )
        if event_id:
            query = query.filter(PaperPosition.event_id == event_id)
        return float(query.scalar() or 0.0)

    def max_drawdown(self, session: Session, initial: float) -> float:
        snapshots = session.query(BankrollSnapshot).order_by(BankrollSnapshot.timestamp_utc.asc()).all()
        peak = initial
        max_dd = 0.0
        for snap in snapshots:
            peak = max(peak, snap.bankroll)
            if peak > 0:
                max_dd = max(max_dd, (peak - snap.bankroll) / peak)
        return max_dd * 100.0

