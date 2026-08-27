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
    kalshi_series_tickers: str = "KXHIGHNY,KXHIGHCHI,KXHIGHMIA,KXHIGHLAX,KXHIGHDEN"
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
