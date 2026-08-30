from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "external-bots" / "freqtrade" / "user_data" / "config.json"
COMPOSE_PATH = ROOT / "docker-compose.freqtrade.yml"
STRATEGY_PATH = ROOT / "external-bots" / "freqtrade" / "user_data" / "strategies" / "WeatherEdgeflowGuardedStrategy.py"


def test_freqtrade_sidecar_is_dry_run_without_credentials() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    assert config["dry_run"] is True
    assert config["trading_mode"] == "spot"
    assert config["exchange"]["key"] == ""
    assert config["exchange"]["secret"] == ""
    assert config["max_open_trades"] <= 2
    assert config["stake_amount"] <= 10
    assert "BTC/USDT" in config["exchange"]["pair_whitelist"]


def test_freqtrade_ui_is_bound_to_localhost_only() -> None:
    compose = COMPOSE_PATH.read_text(encoding="utf-8")

    assert "127.0.0.1:8081:8080" in compose
    assert "freqtradeorg/freqtrade:stable" in compose
    assert "LIVE_CASH" not in compose


def test_freqtrade_strategy_is_spot_only_and_has_stoploss() -> None:
    strategy = STRATEGY_PATH.read_text(encoding="utf-8")

    assert "can_short = False" in strategy
    assert "stoploss = -0.012" in strategy
    assert "populate_entry_trend" in strategy
    assert "populate_exit_trend" in strategy
