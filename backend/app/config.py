from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


Mode = Literal["OBSERVE", "PAPER", "LIVE_SIGNAL"]
Venue = Literal["KALSHI", "POLYMARKET"]


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "WeatherEdgeflow"
    app_env: str = "local"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    database_url: str = "sqlite:///./data/weatheredgeflow.sqlite3"
    log_level: str = "INFO"
    log_file: str = "./logs/weatheredgeflow.log"

    polymarket_gamma_base_url: str = "https://gamma-api.polymarket.com"
    polymarket_clob_base_url: str = "https://clob.polymarket.com"
    polymarket_data_base_url: str = "https://data-api.polymarket.com"
    kalshi_base_url: str = "https://external-api.kalshi.com/trade-api/v2"
    kalshi_series_tickers: str = "KXHIGHNY,KXHIGHCHI,KXHIGHMIA,KXHIGHLAX,KXHIGHDEN,KXHIGHAUS"
    kalshi_weather_source_base_url: str = "https://weather.com/kalshi"
    kalshi_require_official_weather_source: bool = True
    kalshi_min_source_margin_f: float = 2.0
    binance_spot_base_url: str = "https://api.binance.com"
    binance_futures_base_url: str = "https://fapi.binance.com"
    crypto_symbols: str = "BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT,BNBUSDT,ADAUSDT,LINKUSDT,AVAXUSDT,LTCUSDT,BCHUSDT"
    kalshi_crypto_series_tickers: str = "KXBTCMAXY,KXBTCMINY,KXETHMAXY,KXETHMINY,KXXRP15M,KXETH15M,KXSOL15M,KXDOGE15M"
    crypto_min_net_daily_edge: float = 0.001
    crypto_max_spread: float = 0.001
    crypto_max_basis_risk: float = 0.005
    crypto_min_notional_usd: float = 25.0
    crypto_spot_fee_rate: float = 0.001
    crypto_futures_fee_rate: float = 0.0005
    crypto_safety_margin: float = 0.001
    crypto_barrier_vol_window_days: int = 14
    crypto_barrier_min_net_edge: float = 0.15
    crypto_barrier_safety_margin: float = 0.08
    crypto_barrier_max_spread: float = 0.15
    crypto_short_interval_minutes: int = 15
    crypto_short_scan_interval_minutes: int = 5
    crypto_short_min_net_edge: float = 0.18
    crypto_short_safety_margin: float = 0.10
    crypto_short_max_spread: float = 0.08
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True
    alert_email_enabled: bool = False
    alert_email_recipient: str = ""
    alert_min_confidence: float = 70.0
    alert_min_net_edge: float = 0.10
    alert_min_model_probability: float = 0.60
    alert_min_profit_usd_per_1: float = 0.40
    openmeteo_forecast_base_url: str = "https://api.open-meteo.com/v1"
    openmeteo_geocoding_base_url: str = "https://geocoding-api.open-meteo.com/v1"
    noaa_base_url: str = "https://api.weather.gov"
    http_timeout_seconds: float = 12.0

    initial_bankroll_usd: float = 10.0
    paper_bankroll_usd: float = 10.0
    max_position_percent: float = 10.0
    max_position_usd: float = 1.0
    max_total_exposure_percent: float = 25.0
    max_daily_loss_percent: float = 10.0
    max_drawdown_percent: float = 30.0
    min_net_edge: float = 0.10
    min_confidence: int = 55
    max_spread: float = 0.08
    scan_interval_minutes: int = 20
    user_timezone: str = "America/Argentina/Buenos_Aires"
    mode: Mode = "PAPER"
    venue: Venue = "KALSHI"

    safety_margin: float = 0.03
    stale_weather_minutes: int = 180
    stale_market_minutes: int = 20
    actionable_horizon_hours: int = 24
    preferred_horizon_hours: int = 24
    max_markets_per_scan: int = 250

    @field_validator("mode", mode="before")
    @classmethod
    def normalize_mode(cls, value: str) -> str:
        return str(value or "PAPER").upper()

    @field_validator("venue", mode="before")
    @classmethod
    def normalize_venue(cls, value: str) -> str:
        return str(value or "KALSHI").upper()

    @property
    def root_dir(self) -> Path:
        return Path(__file__).resolve().parents[2]


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
