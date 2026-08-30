from __future__ import annotations

from app.domain.algo_decision import (
    AccountState,
    AlgoDecisionInput,
    AlgoRiskParameters,
    AutonomousTradingDecisionEngine,
    Candle,
    IndicatorSnapshot,
)


def _candles(*, count: int = 30, start: float = 100.0, step: float = 0.2) -> list[Candle]:
    rows: list[Candle] = []
    price = start
    for index in range(count):
        close = price + step
        rows.append(Candle(open=price, high=max(price, close) + 0.1, low=min(price, close) - 0.1, close=close, volume=1000 + index))
        price = close
    return rows


def _payload(**overrides) -> AlgoDecisionInput:
    values = {
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "current_price": 106.0,
        "candles": _candles(),
        "indicators": IndicatorSnapshot(
            rsi=58,
            sma_fast=104.0,
            sma_slow=101.0,
            ema_fast=104.4,
            ema_slow=102.0,
            macd=1.2,
            macd_signal=0.8,
            volatility=0.004,
            volume_sma=1000,
        ),
        "account": AccountState(balance_available=100.0),
        "risk": AlgoRiskParameters(
            max_capital_per_trade_pct=2.0,
            max_stop_loss_pct=1.0,
            take_profit_pct=2.0,
            max_simultaneous_trades=2,
            max_daily_drawdown_pct=5.0,
            max_leverage=1.0,
        ),
    }
    values.update(overrides)
    return AlgoDecisionInput(**values)


def test_algo_decision_buys_when_trend_and_momentum_align() -> None:
    decision = AutonomousTradingDecisionEngine().decide(_payload())

    assert decision.accion == "comprar"
    assert decision.tamano_posicion == 2.0
    assert decision.stop_loss == 104.94
    assert decision.take_profit == 108.12
    assert decision.alerta_riesgo is False
    assert decision.confianza >= 70


def test_algo_decision_holds_with_insufficient_data() -> None:
    decision = AutonomousTradingDecisionEngine().decide(_payload(candles=_candles(count=5)))

    assert decision.accion == "mantener"
    assert decision.confianza <= 20
    assert decision.tamano_posicion == "N/A"


def test_algo_decision_blocks_daily_drawdown() -> None:
    decision = AutonomousTradingDecisionEngine().decide(
        _payload(account=AccountState(balance_available=100.0, daily_pnl=-5.1))
    )

    assert decision.accion == "mantener"
    assert decision.alerta_riesgo is True
    assert "Drawdown" in decision.razonamiento


def test_algo_decision_blocks_volatility_anomaly() -> None:
    candles = _candles()
    candles[-1] = Candle(open=100, high=115, low=95, close=114, volume=5000)
    decision = AutonomousTradingDecisionEngine().decide(_payload(candles=candles))

    assert decision.accion == "mantener"
    assert decision.alerta_riesgo is True


def test_algo_decision_respects_cooldown() -> None:
    decision = AutonomousTradingDecisionEngine().decide(
        _payload(account=AccountState(balance_available=100.0, seconds_since_last_trade=60))
    )

    assert decision.accion == "mantener"
    assert "Cooldown" in decision.razonamiento


def test_algo_decision_closes_position_at_stop_loss() -> None:
    decision = AutonomousTradingDecisionEngine().decide(
        _payload(
            current_price=98.5,
            account=AccountState(
                balance_available=100.0,
                current_position_side="long",
                current_position_size=2.0,
                current_position_entry_price=100.0,
            ),
        )
    )

    assert decision.accion == "cerrar_posicion"
    assert decision.alerta_riesgo is True
    assert decision.tamano_posicion == 2.0


def test_algo_decision_holds_short_signal_when_leverage_disallows_short() -> None:
    bearish = IndicatorSnapshot(
        rsi=45,
        sma_fast=101.0,
        sma_slow=104.0,
        ema_fast=101.0,
        ema_slow=103.0,
        macd=-1.0,
        macd_signal=-0.2,
        volatility=0.004,
        volume_sma=1000,
    )
    decision = AutonomousTradingDecisionEngine().decide(
        _payload(current_price=99.0, candles=_candles(start=106, step=-0.2), indicators=bearish)
    )

    assert decision.accion == "mantener"
    assert "short" in decision.razonamiento
