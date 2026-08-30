from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Action = Literal["comprar", "vender", "mantener", "cerrar_posicion"]
PositionSide = Literal["long", "short", "none"]


@dataclass(frozen=True)
class Candle:
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class IndicatorSnapshot:
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


@dataclass(frozen=True)
class AccountState:
    balance_available: float
    open_positions: int = 0
    daily_pnl: float = 0.0
    current_position_side: PositionSide = "none"
    current_position_size: float = 0.0
    current_position_entry_price: float | None = None
    seconds_since_last_trade: int | None = None


@dataclass(frozen=True)
class AlgoRiskParameters:
    max_capital_per_trade_pct: float
    max_stop_loss_pct: float
    take_profit_pct: float
    max_simultaneous_trades: int
    max_daily_drawdown_pct: float
    max_leverage: float = 1.0
    min_cooldown_seconds: int = 180


@dataclass(frozen=True)
class AlgoDecisionInput:
    symbol: str
    timeframe: str
    current_price: float
    candles: list[Candle]
    indicators: IndicatorSnapshot
    account: AccountState
    risk: AlgoRiskParameters


@dataclass(frozen=True)
class AlgoDecision:
    accion: Action
    confianza: int
    tamano_posicion: float | str
    stop_loss: float | str
    take_profit: float | str
    razonamiento: str
    alerta_riesgo: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "accion": self.accion,
            "confianza": self.confianza,
            "tamano_posicion": self.tamano_posicion,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "razonamiento": self.razonamiento,
            "alerta_riesgo": self.alerta_riesgo,
        }


class AutonomousTradingDecisionEngine:
    """Deterministic trading decision engine.

    This engine does not fetch data and does not execute orders. It only turns
    supplied market/account/risk context into a conservative JSON decision.
    """

    min_candles = 20

    def decide(self, payload: AlgoDecisionInput) -> AlgoDecision:
        invalid_reason = self._invalid_reason(payload)
        if invalid_reason:
            return self._hold(20, invalid_reason, alerta=False)

        account = payload.account
        risk = payload.risk
        price = payload.current_price
        daily_stop = -account.balance_available * risk.max_daily_drawdown_pct / 100.0
        if account.daily_pnl <= daily_stop:
            return self._hold(
                5,
                f"Drawdown diario alcanzado: PnL {account.daily_pnl:.2f} <= limite {daily_stop:.2f}.",
                alerta=True,
            )

        anomaly = self._volatility_anomaly(payload)
        if anomaly:
            return self._hold(15, anomaly, alerta=True)

        if account.seconds_since_last_trade is not None and account.seconds_since_last_trade < risk.min_cooldown_seconds:
            return self._hold(
                25,
                f"Cooldown activo: ultima operacion hace {account.seconds_since_last_trade}s, minimo {risk.min_cooldown_seconds}s.",
                alerta=False,
            )

        position_exit = self._position_exit(payload)
        if position_exit is not None:
            return position_exit

        if account.open_positions >= risk.max_simultaneous_trades:
            return self._hold(
                30,
                f"Maximo de operaciones simultaneas alcanzado: {account.open_positions}/{risk.max_simultaneous_trades}.",
                alerta=False,
            )

        bullish, bullish_reasons = self._bullish_score(payload)
        bearish, bearish_reasons = self._bearish_score(payload)
        if bullish >= 4 and bullish - bearish >= 2:
            size = self._position_size(account.balance_available, risk.max_capital_per_trade_pct)
            return AlgoDecision(
                accion="comprar",
                confianza=self._confidence(bullish, bearish),
                tamano_posicion=size,
                stop_loss=round(price * (1.0 - risk.max_stop_loss_pct / 100.0), 8),
                take_profit=round(price * (1.0 + risk.take_profit_pct / 100.0), 8),
                razonamiento="; ".join(bullish_reasons[:3]),
                alerta_riesgo=False,
            )

        if bearish >= 4 and bearish - bullish >= 2:
            if risk.max_leverage <= 1.0 and account.current_position_side == "none":
                return self._hold(35, "Senal bajista, pero max_leverage <= 1 impide abrir short conservador.", alerta=False)
            size = self._position_size(account.balance_available, risk.max_capital_per_trade_pct)
            return AlgoDecision(
                accion="vender",
                confianza=self._confidence(bearish, bullish),
                tamano_posicion=size,
                stop_loss=round(price * (1.0 + risk.max_stop_loss_pct / 100.0), 8),
                take_profit=round(price * (1.0 - risk.take_profit_pct / 100.0), 8),
                razonamiento="; ".join(bearish_reasons[:3]),
                alerta_riesgo=False,
            )

        return self._hold(
            35,
            f"Senales mixtas: score alcista {bullish}, bajista {bearish}; no hay ventaja tecnica suficiente.",
            alerta=False,
        )

    def _invalid_reason(self, payload: AlgoDecisionInput) -> str | None:
        if not payload.symbol or not payload.timeframe:
            return "Datos insuficientes: falta simbolo o timeframe."
        if payload.current_price <= 0:
            return "Datos insuficientes: precio actual invalido."
        if payload.account.balance_available <= 0:
            return "Datos insuficientes: balance disponible invalido."
        if len(payload.candles) < self.min_candles:
            return f"Datos insuficientes: se requieren al menos {self.min_candles} velas."
        required = (
            payload.indicators.rsi,
            payload.indicators.sma_fast,
            payload.indicators.sma_slow,
            payload.indicators.macd,
            payload.indicators.macd_signal,
        )
        if any(value is None for value in required):
            return "Datos insuficientes: faltan RSI, medias o MACD."
        if payload.risk.max_capital_per_trade_pct <= 0 or payload.risk.max_capital_per_trade_pct > 100:
            return "Parametros de riesgo invalidos: capital por operacion fuera de rango."
        if payload.risk.max_stop_loss_pct <= 0 or payload.risk.take_profit_pct <= 0:
            return "Parametros de riesgo invalidos: stop-loss/take-profit deben ser positivos."
        if payload.risk.max_simultaneous_trades < 1:
            return "Parametros de riesgo invalidos: max_simultaneous_trades debe ser >= 1."
        return None

    def _volatility_anomaly(self, payload: AlgoDecisionInput) -> str | None:
        last = payload.candles[-1]
        previous = payload.candles[-2]
        price = payload.current_price
        last_range_pct = (last.high - last.low) / price * 100.0
        last_return_pct = abs(last.close / previous.close - 1.0) * 100.0 if previous.close > 0 else 0.0
        volatility_pct = float(payload.indicators.volatility or 0.0) * 100.0
        volume_sma = payload.indicators.volume_sma
        volume_spike = volume_sma is not None and volume_sma > 0 and last.volume > volume_sma * 3.0
        if last_range_pct > payload.risk.max_stop_loss_pct * 2.0:
            return f"Volatilidad anomala: rango ultima vela {last_range_pct:.2f}% supera umbral conservador."
        if volatility_pct > 0 and last_return_pct > max(payload.risk.max_stop_loss_pct, volatility_pct * 3.0):
            return f"Movimiento anomalo: retorno ultima vela {last_return_pct:.2f}% vs volatilidad {volatility_pct:.2f}%."
        if volume_spike and last_return_pct > payload.risk.max_stop_loss_pct:
            return f"Volumen anomalo: volumen {last.volume:.2f} > 3x promedio y movimiento {last_return_pct:.2f}%."
        return None

    def _position_exit(self, payload: AlgoDecisionInput) -> AlgoDecision | None:
        side = payload.account.current_position_side
        entry = payload.account.current_position_entry_price
        if side == "none" or entry is None or entry <= 0:
            return None
        price = payload.current_price
        pnl_pct = (price / entry - 1.0) * 100.0
        if side == "short":
            pnl_pct *= -1.0
        if pnl_pct <= -payload.risk.max_stop_loss_pct:
            return AlgoDecision(
                accion="cerrar_posicion",
                confianza=90,
                tamano_posicion=payload.account.current_position_size,
                stop_loss="N/A",
                take_profit="N/A",
                razonamiento=f"Stop-loss alcanzado: PnL posicion {pnl_pct:.2f}% <= -{payload.risk.max_stop_loss_pct:.2f}%.",
                alerta_riesgo=True,
            )
        if pnl_pct >= payload.risk.take_profit_pct:
            return AlgoDecision(
                accion="cerrar_posicion",
                confianza=80,
                tamano_posicion=payload.account.current_position_size,
                stop_loss="N/A",
                take_profit="N/A",
                razonamiento=f"Take-profit alcanzado: PnL posicion {pnl_pct:.2f}% >= {payload.risk.take_profit_pct:.2f}%.",
                alerta_riesgo=False,
            )
        return None

    def _bullish_score(self, payload: AlgoDecisionInput) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []
        i = payload.indicators
        price = payload.current_price
        if i.sma_fast is not None and i.sma_slow is not None and price > i.sma_fast > i.sma_slow:
            score += 2
            reasons.append(f"Precio {price:.4f} > SMA rapida {i.sma_fast:.4f} > SMA lenta {i.sma_slow:.4f}")
        if i.ema_fast is not None and i.ema_slow is not None and i.ema_fast > i.ema_slow:
            score += 1
            reasons.append(f"EMA rapida {i.ema_fast:.4f} supera EMA lenta {i.ema_slow:.4f}")
        if i.rsi is not None and 45 <= i.rsi <= 68:
            score += 1
            reasons.append(f"RSI {i.rsi:.1f} en zona alcista sin sobrecompra extrema")
        if i.macd is not None and i.macd_signal is not None and i.macd > i.macd_signal:
            score += 1
            reasons.append(f"MACD {i.macd:.4f} > senal {i.macd_signal:.4f}")
        if self._last_close_momentum(payload) > 0:
            score += 1
            reasons.append("Momentum de cierres recientes positivo")
        return score, reasons

    def _bearish_score(self, payload: AlgoDecisionInput) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []
        i = payload.indicators
        price = payload.current_price
        if i.sma_fast is not None and i.sma_slow is not None and price < i.sma_fast < i.sma_slow:
            score += 2
            reasons.append(f"Precio {price:.4f} < SMA rapida {i.sma_fast:.4f} < SMA lenta {i.sma_slow:.4f}")
        if i.ema_fast is not None and i.ema_slow is not None and i.ema_fast < i.ema_slow:
            score += 1
            reasons.append(f"EMA rapida {i.ema_fast:.4f} debajo de EMA lenta {i.ema_slow:.4f}")
        if i.rsi is not None and 32 <= i.rsi <= 55:
            score += 1
            reasons.append(f"RSI {i.rsi:.1f} compatible con sesgo bajista sin capitulacion extrema")
        if i.macd is not None and i.macd_signal is not None and i.macd < i.macd_signal:
            score += 1
            reasons.append(f"MACD {i.macd:.4f} < senal {i.macd_signal:.4f}")
        if self._last_close_momentum(payload) < 0:
            score += 1
            reasons.append("Momentum de cierres recientes negativo")
        return score, reasons

    def _last_close_momentum(self, payload: AlgoDecisionInput) -> float:
        closes = [candle.close for candle in payload.candles[-5:] if candle.close > 0]
        if len(closes) < 2:
            return 0.0
        return closes[-1] - closes[0]

    def _position_size(self, balance: float, max_pct: float) -> float:
        return round(max(0.0, balance * max_pct / 100.0), 2)

    def _confidence(self, winning_score: int, losing_score: int) -> int:
        return max(45, min(85, 45 + winning_score * 7 + max(0, winning_score - losing_score) * 4))

    def _hold(self, confidence: int, reason: str, *, alerta: bool) -> AlgoDecision:
        return AlgoDecision(
            accion="mantener",
            confianza=confidence,
            tamano_posicion="N/A",
            stop_loss="N/A",
            take_profit="N/A",
            razonamiento=reason,
            alerta_riesgo=alerta,
        )
