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


class AlgoCandle(BaseModel):
    open: float
    high: float
    low: float
    close: float
    volume: float


class AlgoIndicators(BaseModel):
    rsi: float | None = None
    sma_fast: float | None = None
    sma_slow: float | None = None
    ema_fast: float | None = None
    ema_slow: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    atr: float | None = None
    volatility: float | None = None
    volume_sma: float | None = None


class AlgoAccountState(BaseModel):
    balance_available: float
    open_positions: int = 0
    daily_pnl: float = 0.0
    current_position_side: Literal["long", "short", "none"] = "none"
    current_position_size: float = 0.0
    current_position_entry_price: float | None = None
    seconds_since_last_trade: int | None = None


class AlgoRiskParameters(BaseModel):
    max_capital_per_trade_pct: float
    max_stop_loss_pct: float
    take_profit_pct: float
    max_simultaneous_trades: int
    max_daily_drawdown_pct: float
    max_leverage: float = 1.0
    min_cooldown_seconds: int = 180


class AlgoDecisionRequest(BaseModel):
    symbol: str
    timeframe: str
    current_price: float
    candles: list[AlgoCandle]
    indicators: AlgoIndicators
    account: AlgoAccountState
    risk: AlgoRiskParameters
