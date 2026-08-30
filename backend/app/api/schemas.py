from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SettingsUpdate(BaseModel):
    updates: dict[str, Any]
    confirmed: bool = False


class ControlUpdate(BaseModel):
    paused: bool | None = None
    kill_switch: bool | None = None
    confirmed: bool = False


class ScanResponse(BaseModel):
    status: str
    errors: int = 0
    opportunities: int = 0


class ModeUpdate(BaseModel):
    mode: Literal["OBSERVE", "PAPER", "LIVE_SIGNAL"]
    confirmed: bool = Field(default=True)


class LiveExecutionPreflightRequest(BaseModel):
    source: Literal["weather", "crypto"]
    signal_id: int
    stop_loss_price: float | None = None
    force: bool = False
