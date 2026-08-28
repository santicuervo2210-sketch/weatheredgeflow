from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.config import AppSettings
from app.db.models import Setting
from app.utils.time import utc_now


SENSITIVE_KEYS = {
    "bankroll_usd",
    "paper_bankroll_usd",
    "min_net_edge",
    "max_position_usd",
    "max_position_percent",
    "max_total_exposure_percent",
    "max_daily_loss_percent",
    "max_drawdown_percent",
}


@dataclass(frozen=True)
class RuntimeSettings:
    language: str
    venue: str
    mode: str
    bankroll_usd: float
    paper_bankroll_usd: float
    scan_interval_minutes: int
    min_net_edge: float
    max_position_usd: float
    max_position_percent: float
    max_total_exposure_percent: float
    max_daily_loss_percent: float
    max_drawdown_percent: float
    min_confidence: float
    max_spread: float
    preferred_horizon_hours: int
    user_timezone: str
    alert_email_enabled: bool
    alert_email_recipient: str
    alert_min_confidence: float
    alert_min_net_edge: float
    alert_min_model_probability: float
    alert_min_profit_usd_per_1: float
    paused: bool
    kill_switch: bool

    @property
    def active_bankroll(self) -> float:
        return self.paper_bankroll_usd if self.mode == "PAPER" else self.bankroll_usd


class SettingsService:
    def __init__(self, app_settings: AppSettings) -> None:
        self.app_settings = app_settings

    def defaults(self) -> dict[str, Any]:
        return {
            "language": "es",
            "venue": self.app_settings.venue,
            "mode": self.app_settings.mode,
            "bankroll_usd": self.app_settings.initial_bankroll_usd,
            "paper_bankroll_usd": self.app_settings.paper_bankroll_usd,
            "scan_interval_minutes": self.app_settings.scan_interval_minutes,
            "min_net_edge": self.app_settings.min_net_edge,
            "max_position_usd": self.app_settings.max_position_usd,
            "max_position_percent": self.app_settings.max_position_percent,
            "max_total_exposure_percent": self.app_settings.max_total_exposure_percent,
            "max_daily_loss_percent": self.app_settings.max_daily_loss_percent,
            "max_drawdown_percent": self.app_settings.max_drawdown_percent,
            "min_confidence": self.app_settings.min_confidence,
            "max_spread": self.app_settings.max_spread,
            "preferred_horizon_hours": self.app_settings.preferred_horizon_hours,
            "user_timezone": self.app_settings.user_timezone,
            "alert_email_enabled": self.app_settings.alert_email_enabled,
            "alert_email_recipient": self.app_settings.alert_email_recipient,
            "alert_min_confidence": self.app_settings.alert_min_confidence,
            "alert_min_net_edge": self.app_settings.alert_min_net_edge,
            "alert_min_model_probability": self.app_settings.alert_min_model_probability,
            "alert_min_profit_usd_per_1": self.app_settings.alert_min_profit_usd_per_1,
            "paused": False,
            "kill_switch": False,
        }

    def initialize(self, session: Session) -> None:
        existing = {row.key for row in session.query(Setting).all()}
        for key, value in self.defaults().items():
            if key in existing:
                continue
            session.add(Setting(key=key, value=json.dumps(value), updated_at_utc=utc_now()))
        session.flush()

    def get_all(self, session: Session) -> dict[str, Any]:
        values = self.defaults()
        for row in session.query(Setting).all():
            values[row.key] = _loads(row.value)
        return values

    def get_runtime(self, session: Session) -> RuntimeSettings:
        values = self.get_all(session)
        return RuntimeSettings(
            language=str(values["language"]),
            venue=str(values["venue"]).upper(),
            mode=str(values["mode"]).upper(),
            bankroll_usd=float(values["bankroll_usd"]),
            paper_bankroll_usd=float(values["paper_bankroll_usd"]),
            scan_interval_minutes=int(values["scan_interval_minutes"]),
            min_net_edge=float(values["min_net_edge"]),
            max_position_usd=float(values["max_position_usd"]),
            max_position_percent=float(values["max_position_percent"]),
            max_total_exposure_percent=float(values["max_total_exposure_percent"]),
            max_daily_loss_percent=float(values["max_daily_loss_percent"]),
            max_drawdown_percent=float(values["max_drawdown_percent"]),
            min_confidence=float(values["min_confidence"]),
            max_spread=float(values["max_spread"]),
            preferred_horizon_hours=int(values["preferred_horizon_hours"]),
            user_timezone=str(values["user_timezone"]),
            alert_email_enabled=bool(values["alert_email_enabled"]),
            alert_email_recipient=str(values["alert_email_recipient"]),
            alert_min_confidence=float(values["alert_min_confidence"]),
            alert_min_net_edge=float(values["alert_min_net_edge"]),
            alert_min_model_probability=float(values["alert_min_model_probability"]),
            alert_min_profit_usd_per_1=float(values["alert_min_profit_usd_per_1"]),
            paused=bool(values["paused"]),
            kill_switch=bool(values["kill_switch"]),
        )

    def update(self, session: Session, updates: dict[str, Any], *, confirmed: bool = False) -> dict[str, Any]:
        unknown = set(updates) - set(self.defaults())
        if unknown:
            raise ValueError(f"Unknown settings: {', '.join(sorted(unknown))}")
        sensitive = set(updates) & SENSITIVE_KEYS
        if sensitive and not confirmed:
            raise PermissionError(f"Sensitive settings require confirmation: {', '.join(sorted(sensitive))}")
        for key, value in updates.items():
            row = session.get(Setting, key)
            if row is None:
                row = Setting(key=key, value=json.dumps(value), updated_at_utc=utc_now())
                session.add(row)
            else:
                row.value = json.dumps(value)
                row.updated_at_utc = utc_now()
        session.flush()
        return self.get_all(session)


def _loads(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value
