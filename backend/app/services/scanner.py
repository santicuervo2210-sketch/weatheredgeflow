from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import replace
from datetime import timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.clients.http import PublicAPIError
from app.clients.kalshi import KalshiClient
from app.clients.polymarket import PolymarketClient
from app.clients.weather import NOAAProvider, OpenMeteoProvider, TheWeatherCompanyKalshiProvider
from app.config import AppSettings
from app.db.models import (
    Market,
    MarketOutcome,
    PaperOrder,
    PaperPosition,
    Resolution,
    Scan,
    Signal,
    WeatherForecast,
    WeatherObservation,
)
from app.db.session import session_scope
from app.domain.edge import EdgeCalculator
from app.domain.kalshi_parser import KalshiWeatherMarketParser
from app.domain.liquidity import LiquidityFilter
from app.domain.market_parser import WeatherMarketParser
from app.domain.paper import PaperExecutionEngine, calculate_resolved_pnl
from app.domain.probability import ProbabilityEngine
from app.domain.resolution import ResolutionEngine
from app.domain.risk import RiskLimits, RiskManager
from app.domain.types import (
    FeeSchedule,
    ForecastBundle,
    ObservationSnapshot,
    OrderBookSnapshot,
    ParseFailure,
    ParsedOutcome,
    ParsedWeatherMarket,
)
from app.services.events import log_event
from app.services.notifications import NotificationService
from app.services.portfolio import PortfolioService
from app.services.settings_service import RuntimeSettings, SettingsService
from app.utils.time import parse_datetime, utc_now


logger = logging.getLogger(__name__)


class ScannerService:
    def __init__(self, app_settings: AppSettings, settings_service: SettingsService) -> None:
        self.app_settings = app_settings
        self.settings_service = settings_service
        self.parser = WeatherMarketParser()
        self.kalshi_parser = KalshiWeatherMarketParser()
        self.probability_engine = ProbabilityEngine()
        self.edge_calculator = EdgeCalculator()
        self.liquidity_filter = LiquidityFilter()
        self.risk_manager = RiskManager()
        self.paper_engine = PaperExecutionEngine()
        self.resolution_engine = ResolutionEngine()
        self.portfolio = PortfolioService()
        self.notifications = NotificationService(app_settings)
        self._lock = asyncio.Lock()
        self.last_scan_started_at = None
        self.last_scan_finished_at = None
        self.last_scan_error = None

    async def run_once(self) -> dict[str, Any]:
        if self._lock.locked():
            return {"status": "SKIPPED", "reason": "SCAN_ALREADY_RUNNING"}
        async with self._lock:
            self.last_scan_started_at = utc_now()
            start = time.perf_counter()
            with session_scope() as session:
                runtime = self.settings_service.get_runtime(session)
                scan = Scan(started_at_utc=utc_now(), mode=runtime.mode, status="RUNNING")
                session.add(scan)
                session.flush()
                log_event(session, message_es="Scanner iniciado", message_en="Scanner started")
                session.flush()
                scan_id = scan.id

            venue_name = runtime.venue
            market_client = KalshiClient(self.app_settings) if venue_name == "KALSHI" else PolymarketClient(self.app_settings)
            parser = self.kalshi_parser if venue_name == "KALSHI" else self.parser
            openmeteo = OpenMeteoProvider(self.app_settings)
            noaa = NOAAProvider(self.app_settings)
            twc = TheWeatherCompanyKalshiProvider(self.app_settings)
            errors = 0
            opportunities = 0
            weather_markets: list[dict[str, Any]] = []
            geo_cache: dict[tuple[str, str | None], Any] = {}
            weather_cache: dict[tuple[float, float, str, str, str], ForecastBundle] = {}
            obs_cache: dict[tuple[float, float, str, str], ObservationSnapshot | None] = {}
            try:
                weather_markets = await market_client.get_weather_markets(limit=self.app_settings.max_markets_per_scan)
                with session_scope() as session:
                    scan = session.get(Scan, scan_id)
                    if scan:
                        scan.markets_found = len(weather_markets)
                        scan.weather_markets_found = len(weather_markets)
                    log_event(
                        session,
                        message_es=f"{len(weather_markets)} mercados meteorológicos recibidos desde {venue_name}",
                        message_en=f"{len(weather_markets)} weather markets received from {venue_name}",
                    )
                for raw_market in weather_markets:
                    try:
                        result = parser.parse(raw_market)
                        if isinstance(result, ParseFailure):
                            with session_scope() as session:
                                self._save_parse_failure(session, scan_id, result)
                            continue
                        supported_created = await self._process_market(
                            session_id=scan_id,
                            market=result,
                            raw_market=raw_market,
                            runtime=runtime,
                            poly=market_client,
                            openmeteo=openmeteo,
                            noaa=noaa,
                            twc=twc,
                            geo_cache=geo_cache,
                            weather_cache=weather_cache,
                            obs_cache=obs_cache,
                        )
                        opportunities += supported_created
                    except Exception as exc:  # noqa: BLE001
                        errors += 1
                        logger.exception("scan market failed")
                        with session_scope() as session:
                            log_event(
                                session,
                                message_es=f"Error procesando mercado: {exc}",
                                message_en=f"Error processing market: {exc}",
                                level="ERROR",
                                details={"market": raw_market.get("id")},
                        )
                await self._update_open_positions(market_client)
            except Exception as exc:  # noqa: BLE001
                errors += 1
                self.last_scan_error = str(exc)
                logger.exception("scanner failed")
                with session_scope() as session:
                    log_event(
                        session,
                        message_es=f"Error consultando {venue_name}: {exc}",
                        message_en=f"Error fetching {venue_name}: {exc}",
                        level="ERROR",
                    )
            finally:
                await market_client.close()
                await openmeteo.close()
                await noaa.close()
                await twc.close()

            elapsed_ms = int((time.perf_counter() - start) * 1000)
            with session_scope() as session:
                runtime = self.settings_service.get_runtime(session)
                scan = session.get(Scan, scan_id)
                if scan:
                    scan.finished_at_utc = utc_now()
                    scan.status = "COMPLETED" if errors == 0 else "DEGRADED"
                    scan.errors_count = errors
                    scan.opportunities_found = opportunities
                    scan.supported_markets = int(
                        session.query(func.count(func.distinct(Signal.market_id)))
                        .filter(Signal.scan_id == scan_id, Signal.city.is_not(None))
                        .scalar()
                        or 0
                    )
                    scan.duration_ms = elapsed_ms
                    scan.next_scan_at_utc = utc_now() + timedelta(minutes=runtime.scan_interval_minutes)
                    scan.summary_es = (
                        f"Analizando {runtime.venue}...\n"
                        f"Mercados meteorológicos encontrados: {scan.weather_markets_found}\n"
                        f"Mercados compatibles: {scan.supported_markets}\n"
                        f"Oportunidades: {scan.opportunities_found}"
                    )
                    scan.summary_en = (
                        f"Scanning {runtime.venue}...\n"
                        f"Weather markets found: {scan.weather_markets_found}\n"
                        f"Supported markets: {scan.supported_markets}\n"
                        f"Opportunities: {scan.opportunities_found}"
                    )
                self.portfolio.snapshot(session, runtime)
                log_event(
                    session,
                    message_es=f"Scanner finalizado en {elapsed_ms} ms",
                    message_en=f"Scanner finished in {elapsed_ms} ms",
                    details={"errors": errors, "opportunities": opportunities},
                )
            self.last_scan_finished_at = utc_now()
            return {"status": "COMPLETED" if errors == 0 else "DEGRADED", "errors": errors, "opportunities": opportunities}

    async def _process_market(
        self,
        *,
        session_id: int,
        market: ParsedWeatherMarket,
        raw_market: dict[str, Any],
        runtime: RuntimeSettings,
        poly: Any,
        openmeteo: OpenMeteoProvider,
        noaa: NOAAProvider,
        twc: TheWeatherCompanyKalshiProvider,
        geo_cache: dict[tuple[str, str | None], Any],
        weather_cache: dict[tuple[float, float, str, str, str], ForecastBundle],
        obs_cache: dict[tuple[float, float, str, str], ObservationSnapshot | None],
    ) -> int:
        with session_scope() as session:
            self._upsert_market(session, market)
            log_event(
                session,
                message_es=f"Mercado compatible: {market.city} {market.target_date.isoformat()}",
                message_en=f"Supported market: {market.city} {market.target_date.isoformat()}",
            )
        geo_key = (market.city.lower(), market.country.lower() if market.country else None)
        if geo_key not in geo_cache:
            geo_cache[geo_key] = await openmeteo.geocode(market.city, market.country)
        location = geo_cache[geo_key]
        if location is None:
            with session_scope() as session:
                for outcome in market.outcomes:
                    self._save_no_trade(
                        session,
                        session_id,
                        market,
                        outcome,
                        "AMBIGUOUS_LOCATION",
                        "No se pudo geocodificar la ciudad.",
                        "Could not geocode city.",
                    )
            return 0

        market = replace(market, timezone=location.timezone, country=location.country or market.country)
        signed_hours = _signed_hours_to_resolution(market)
        if signed_hours < 0:
            with session_scope() as session:
                for outcome in market.outcomes:
                    self._save_no_trade(
                        session,
                        session_id,
                        market,
                        outcome,
                        "EXPIRED_MARKET",
                        "La fecha meteorológica objetivo ya finalizó.",
                        "The target weather date has already ended.",
                    )
            return 0
        hours = max(0.0, signed_hours)
        if hours > runtime.preferred_horizon_hours:
            with session_scope() as session:
                for outcome in market.outcomes:
                    self._save_no_trade(
                        session,
                        session_id,
                        market,
                        outcome,
                        "HORIZON_TOO_LONG",
                        "Mercado fuera del horizonte accionable V1.",
                        "Market is outside V1 actionable horizon.",
                    )
            return 0
        weather_key = (round(location.latitude, 4), round(location.longitude, 4), market.weather_metric, market.target_date.isoformat(), market.unit)
        if weather_key not in weather_cache:
            weather_cache[weather_key] = await openmeteo.fetch_bundle(location, market.weather_metric, market.target_date, market.unit)
        bundle = weather_cache[weather_key]
        obs_key = (round(location.latitude, 4), round(location.longitude, 4), market.target_date.isoformat(), market.unit)
        if obs_key not in obs_cache:
            observation = None
            is_kalshi_twc_market = market.market_id.startswith("KALSHI:") and "Weather Company" in market.resolution_rules
            if is_kalshi_twc_market:
                try:
                    observation = await twc.fetch_observation(
                        market.resolution_station,
                        market.city,
                        market.target_date,
                        market.unit,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.info("Weather Company unavailable for %s: %s", market.city, exc)
            if observation is None:
                observation = await openmeteo.fetch_observation(location, market.target_date, market.unit)
                try:
                    noaa_obs = await noaa.fetch_observation(location, market.target_date, market.unit)
                    if noaa_obs is not None and not is_kalshi_twc_market:
                        observation = noaa_obs
                except Exception as exc:  # noqa: BLE001
                    logger.info("NOAA unavailable for %s: %s", market.city, exc)
            obs_cache[obs_key] = observation
        observation = obs_cache[obs_key]

        with session_scope() as session:
            self._save_weather(session, session_id, market, bundle, observation)
            log_event(
                session,
                message_es=f"Pronóstico obtenido para {market.city}",
                message_en=f"Forecast fetched for {market.city}",
            )

        token_ids = [outcome.token_id for outcome in market.outcomes if outcome.token_id]
        tentative_stake = min(runtime.max_position_usd, runtime.active_bankroll * runtime.max_position_percent / 100.0)
        gamma_min_order_size = _float_or_none(raw_market.get("orderMinSize") or raw_market.get("order_min_size"))
        if gamma_min_order_size is not None and tentative_stake < gamma_min_order_size:
            orderbooks = {}
        else:
            try:
                orderbooks = await poly.get_orderbooks(token_ids)
            except PublicAPIError as exc:
                logger.info("batch orderbook unavailable for %s: %s", market.market_id, exc)
                orderbooks = None

        created_opportunities = 0
        for outcome in market.outcomes:
            try:
                created = await self._process_outcome(
                    session_id=session_id,
                    market=market,
                    outcome=outcome,
                    bundle=bundle,
                    observation=observation,
                    runtime=runtime,
                    poly=poly,
                    raw_market=raw_market,
                    orderbooks=orderbooks,
                )
                created_opportunities += 1 if created else 0
            except Exception as exc:  # noqa: BLE001
                logger.exception("outcome processing failed")
                with session_scope() as session:
                    self._save_no_trade(
                        session,
                        session_id,
                        market,
                        outcome,
                        "ENGINE_ERROR",
                        f"Error del motor: {exc}",
                        f"Engine error: {exc}",
                    )
        return created_opportunities

    async def _update_open_positions(self, poly: Any) -> None:
        with session_scope() as session:
            positions = session.query(PaperPosition).filter(PaperPosition.status == "OPEN").all()
            market_ids = sorted({position.market_id for position in positions})
        for market_id in market_ids:
            try:
                raw_market = await poly.get_market(market_id)
            except Exception as exc:  # noqa: BLE001
                logger.info("resolution fetch failed for %s: %s", market_id, exc)
                continue
            winning_token_id, winning_outcome = self.resolution_engine.extract_winner(raw_market)
            if not winning_token_id and not winning_outcome:
                continue
            with session_scope() as session:
                existing = session.query(Resolution).filter(Resolution.market_id == market_id).one_or_none()
                if existing is None:
                    session.add(
                        Resolution(
                            market_id=market_id,
                            winning_token_id=winning_token_id,
                            winning_outcome=winning_outcome,
                            resolved_at_utc=utc_now(),
                            source=str(raw_market.get("resolutionSource") or ""),
                            raw_json=json.dumps(raw_market, default=str),
                        )
                    )
                for position in session.query(PaperPosition).filter(PaperPosition.market_id == market_id, PaperPosition.status == "OPEN").all():
                    won = bool(
                        (winning_token_id and position.token_id == winning_token_id)
                        or (winning_outcome and position.outcome.lower() == winning_outcome.lower())
                    )
                    gross_pnl, net_pnl = calculate_resolved_pnl(
                        shares=position.shares,
                        entry_cost=position.stake_usd,
                        entry_fees=position.fees,
                        won=won,
                    )
                    position.status = "WIN" if won else "LOSS"
                    position.resolved_at_utc = utc_now()
                    position.gross_pnl = gross_pnl
                    position.net_pnl = net_pnl
                    order = session.get(PaperOrder, position.order_id)
                    if order:
                        order.status = position.status
                        order.pnl = net_pnl
                log_event(
                    session,
                    message_es=f"Mercado resuelto: {market_id}",
                    message_en=f"Market resolved: {market_id}",
                    category="RESOLUTION",
                    details={"winner": winning_outcome, "winning_token_id": winning_token_id},
                )

    async def _process_outcome(
        self,
        *,
        session_id: int,
        market: ParsedWeatherMarket,
        outcome: ParsedOutcome,
        bundle: ForecastBundle,
        observation: ObservationSnapshot | None,
        runtime: RuntimeSettings,
        poly: Any,
        raw_market: dict[str, Any],
        orderbooks: dict[str, OrderBookSnapshot] | None,
    ) -> bool:
        try:
            probability = self.probability_engine.estimate(market, outcome, bundle.forecasts, observation)
        except Exception as exc:  # noqa: BLE001
            with session_scope() as session:
                self._save_no_trade(session, session_id, market, outcome, "PROBABILITY_ENGINE_ERROR", str(exc), str(exc))
            return False

        source_guard = self._official_source_guard(market, outcome, observation)
        if source_guard is not None:
            reason_code, reason_es, reason_en = source_guard
            with session_scope() as session:
                self._save_no_trade(
                    session,
                    session_id,
                    market,
                    outcome,
                    reason_code,
                    reason_es,
                    reason_en,
                    probability=probability,
                )
            return False

        tentative_stake = min(runtime.max_position_usd, runtime.active_bankroll * runtime.max_position_percent / 100.0)
        gamma_min_order_size = _float_or_none(raw_market.get("orderMinSize") or raw_market.get("order_min_size"))
        if gamma_min_order_size is not None and tentative_stake < gamma_min_order_size:
            with session_scope() as session:
                self._save_no_trade(
                    session,
                    session_id,
                    market,
                    outcome,
                    "BELOW_MIN_ORDER",
                    f"Stake recomendado ${tentative_stake:.2f} menor al mínimo de orden ${gamma_min_order_size:.2f}.",
                    f"Recommended stake ${tentative_stake:.2f} is below the ${gamma_min_order_size:.2f} minimum order size.",
                    probability=probability,
                )
            return False
        try:
            orderbook = orderbooks.get(outcome.token_id) if orderbooks is not None else None
            if orderbook is None and orderbooks is None:
                orderbook = await poly.get_orderbook(outcome.token_id)
            if orderbook is None:
                raise PublicAPIError("Order book missing from batch response")
        except PublicAPIError as exc:
            with session_scope() as session:
                self._save_no_trade(
                    session,
                    session_id,
                    market,
                    outcome,
                    "NO_ORDERBOOK",
                    f"Libro no disponible: {exc}",
                    f"Order book unavailable: {exc}",
                    probability=probability,
                )
            return False
        fee_schedule = poly.fee_schedule_from_market(raw_market, outcome.token_id)
        if fee_schedule is None:
            try:
                fee_schedule = await poly.get_fee_rate(outcome.token_id)
            except PublicAPIError:
                fee_schedule = None
        liquidity = self.liquidity_filter.assess(orderbook, stake_usd=tentative_stake, max_spread=runtime.max_spread)
        edge = self.edge_calculator.calculate(
            model_probability=probability.probability,
            orderbook=orderbook,
            fee_schedule=fee_schedule,
            stake_usd=tentative_stake,
            uncertainty_penalty=probability.uncertainty * (1.0 - probability.confidence_score / 100.0),
            safety_margin=self.app_settings.safety_margin,
            min_net_edge=runtime.min_net_edge,
        )
        with session_scope() as session:
            metrics = self.portfolio.metrics(session, runtime)
            open_exposure = self.portfolio.grouped_open_exposure(session)
            event_exposure = self.portfolio.event_open_exposure(session, market.event_id)
            risk = self.risk_manager.assess(
                limits=RiskLimits(
                    bankroll=runtime.active_bankroll,
                    max_position_percent=runtime.max_position_percent,
                    max_position_usd=runtime.max_position_usd,
                    max_total_exposure_percent=runtime.max_total_exposure_percent,
                    max_daily_loss_percent=runtime.max_daily_loss_percent,
                    max_drawdown_percent=runtime.max_drawdown_percent,
                    min_confidence=runtime.min_confidence,
                ),
                requested_stake=tentative_stake,
                open_exposure=open_exposure,
                grouped_event_exposure=event_exposure,
                daily_pnl=metrics["today_pnl"],
                drawdown_percent=metrics["max_drawdown"],
                net_edge=edge.net_edge,
                confidence=probability.confidence_score,
            )
            actionable = (
                edge.action == "BUY"
                and liquidity.ok
                and risk.approved
                and not runtime.paused
                and not runtime.kill_switch
                and runtime.mode in {"PAPER", "LIVE_SIGNAL"}
            )
            action = self._action_for(runtime.mode, outcome, actionable)
            status = "OPPORTUNITY" if actionable else ("OBSERVE" if runtime.mode == "OBSERVE" else "REJECTED")
            reason_code, reason_es, reason_en = self._reason(edge.reason_code, liquidity, risk, runtime)
            signal = self._save_signal(
                session,
                session_id,
                market,
                outcome,
                probability,
                orderbook,
                fee_schedule,
                edge,
                risk,
                action=action,
                status=status,
                reason_code=reason_code,
                reason_es=reason_es,
                reason_en=reason_en,
                liquidity_usd=liquidity.liquidity_usd,
                bundle=bundle,
                observation=observation,
            )
            self.notifications.maybe_notify_weather_signal(session, signal, runtime)
            if actionable and runtime.mode == "PAPER" and fee_schedule is not None:
                fill = self.paper_engine.simulate_buy(
                    orderbook=orderbook,
                    requested_price=edge.executable_price,
                    stake_usd=risk.recommended_stake,
                    fee_schedule=fee_schedule,
                )
                order = PaperOrder(
                    signal_id=signal.id,
                    market_id=market.market_id,
                    token_id=outcome.token_id,
                    side=action,
                    requested_price=edge.executable_price,
                    simulated_fill_price=fill.fill_price,
                    stake_usd=risk.recommended_stake,
                    shares=fill.shares,
                    fees=fill.fees,
                    status=fill.status,
                )
                session.add(order)
                session.flush()
                if fill.status in {"FILLED", "PARTIALLY_FILLED"} and fill.fill_price and fill.shares:
                    session.add(
                        PaperPosition(
                            order_id=order.id,
                            market_id=market.market_id,
                            token_id=outcome.token_id,
                            event_id=market.event_id,
                            outcome=outcome.label,
                            entry_price=fill.fill_price,
                            shares=fill.shares,
                            stake_usd=risk.recommended_stake,
                            fees=fill.fees,
                            status="OPEN",
                        )
                    )
                    log_event(
                        session,
                        message_es="Orden PAPER creada y llenada",
                        message_en="PAPER order created and filled",
                        details={"market_id": market.market_id, "stake": risk.recommended_stake},
                    )
            else:
                log_event(
                    session,
                    message_es=f"{market.city} edge {edge.net_edge * 100:.1f}% - {status.lower()}",
                    message_en=f"{market.city} edge {edge.net_edge * 100:.1f}% - {status.lower()}",
                    details={"market_id": market.market_id, "reason": reason_code},
                )
        return actionable

    def _upsert_market(self, session: Session, market: ParsedWeatherMarket) -> None:
        row = session.query(Market).filter(Market.market_id == market.market_id).one_or_none()
        raw_json = json.dumps(market.raw_market, default=str)
        end_date = parse_datetime(
            str(
                market.raw_market.get("endDate")
                or market.raw_market.get("end_date")
                or market.raw_market.get("close_time")
                or market.raw_market.get("expected_expiration_time")
                or ""
            )
        )
        if row is None:
            row = Market(
                event_id=market.event_id,
                market_id=market.market_id,
                condition_id=market.condition_id,
                question=market.question,
                slug=market.slug,
                category=str(market.raw_market.get("category") or ""),
                polymarket_url=market.polymarket_url,
                active=True,
                closed=False,
                end_date_utc=end_date,
                raw_json=raw_json,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            session.add(row)
            session.flush()
        else:
            row.event_id = market.event_id
            row.condition_id = market.condition_id
            row.question = market.question
            row.slug = market.slug
            row.polymarket_url = market.polymarket_url
            row.end_date_utc = end_date
            row.raw_json = raw_json
            row.updated_at = utc_now()
        for outcome in market.outcomes:
            exists = (
                session.query(MarketOutcome)
                .filter(MarketOutcome.market_id == market.market_id, MarketOutcome.token_id == outcome.token_id)
                .one_or_none()
            )
            if exists is None:
                session.add(
                    MarketOutcome(
                        market_ref_id=row.id,
                        market_id=market.market_id,
                        token_id=outcome.token_id,
                        outcome=outcome.label,
                        side=outcome.side,
                        lower_bound=outcome.lower_bound,
                        upper_bound=outcome.upper_bound,
                        unit=outcome.unit,
                        created_at=utc_now(),
                    )
                )
        session.flush()

    def _save_weather(
        self,
        session: Session,
        scan_id: int,
        market: ParsedWeatherMarket,
        bundle: ForecastBundle,
        observation: ObservationSnapshot | None,
    ) -> None:
        for forecast in bundle.forecasts:
            session.add(
                WeatherForecast(
                    scan_id=scan_id,
                    market_id=market.market_id,
                    provider=forecast.provider,
                    model_name=forecast.model_name,
                    city=market.city,
                    country=market.country,
                    timezone=market.timezone,
                    latitude=bundle.location.latitude,
                    longitude=bundle.location.longitude,
                    weather_metric=forecast.metric,
                    target_date=forecast.target_date.isoformat(),
                    value=forecast.value,
                    unit=forecast.unit,
                    issued_at_utc=forecast.issued_at_utc,
                    fetched_at_utc=forecast.fetched_at_utc,
                    raw_json=json.dumps(forecast.raw, default=str),
                )
            )
        if observation:
            session.add(
                WeatherObservation(
                    scan_id=scan_id,
                    market_id=market.market_id,
                    provider=observation.provider,
                    station=observation.station,
                    observed_max=observation.observed_max,
                    observed_min=observation.observed_min,
                    current_temperature=observation.current_temperature,
                    unit=observation.unit,
                    observed_at_utc=observation.observed_at_utc,
                    fetched_at_utc=observation.fetched_at_utc,
                    raw_json=json.dumps(observation.raw, default=str),
                )
            )
        session.flush()

    def _save_parse_failure(self, session: Session, scan_id: int, failure: ParseFailure) -> None:
        session.add(
            Signal(
                scan_id=scan_id,
                market_id=failure.market_id or "unknown",
                event_id=failure.event_id,
                question=failure.question or "Unknown question",
                action="NO_TRADE",
                status="DISCARDED",
                reason_code=failure.reason_code,
                reason_es=failure.reason_es,
                reason_en=failure.reason_en,
                created_at_utc=utc_now(),
            )
        )
        log_event(session, message_es=f"Mercado descartado: {failure.reason_code}", message_en=f"Market skipped: {failure.reason_code}")

    def _save_no_trade(
        self,
        session: Session,
        scan_id: int,
        market: ParsedWeatherMarket,
        outcome: ParsedOutcome,
        reason_code: str,
        reason_es: str,
        reason_en: str,
        probability: Any | None = None,
    ) -> None:
        session.add(
            Signal(
                scan_id=scan_id,
                market_id=market.market_id,
                token_id=outcome.token_id,
                event_id=market.event_id,
                question=market.question,
                city=market.city,
                country=market.country,
                target_date=market.target_date.isoformat(),
                timezone=market.timezone,
                weather_metric=market.weather_metric,
                outcome=outcome.label,
                action="NO_TRADE",
                status="REJECTED",
                reason_code=reason_code,
                reason_es=reason_es,
                reason_en=reason_en,
                model_probability=getattr(probability, "probability", None),
                confidence=getattr(probability, "confidence_score", None),
                resolution_source=market.resolution_source,
                resolution_station=market.resolution_station,
                resolution_rules=market.resolution_rules,
                polymarket_url=market.polymarket_url,
                distribution_json=json.dumps(getattr(probability, "distribution", {}) or {}),
                created_at_utc=utc_now(),
            )
        )
        log_event(session, message_es=f"{market.city} - NO TRADE: {reason_code}", message_en=f"{market.city} - NO TRADE: {reason_code}")

    def _save_signal(
        self,
        session: Session,
        scan_id: int,
        market: ParsedWeatherMarket,
        outcome: ParsedOutcome,
        probability: Any,
        orderbook: Any,
        fee_schedule: FeeSchedule | None,
        edge: Any,
        risk: Any,
        *,
        action: str,
        status: str,
        reason_code: str,
        reason_es: str,
        reason_en: str,
        liquidity_usd: float,
        bundle: ForecastBundle,
        observation: ObservationSnapshot | None,
    ) -> Signal:
        explanation_es, explanation_en = deterministic_explanation(
            edge.market_probability,
            probability.probability,
            edge.net_edge,
            outcome.label,
        )
        if status == "OPPORTUNITY":
            reason_es = explanation_es
            reason_en = explanation_en
        signal = Signal(
            scan_id=scan_id,
            market_id=market.market_id,
            token_id=outcome.token_id,
            event_id=market.event_id,
            question=market.question,
            city=market.city,
            country=market.country,
            target_date=market.target_date.isoformat(),
            timezone=market.timezone,
            weather_metric=market.weather_metric,
            outcome=outcome.label,
            side="BUY_NO" if outcome.side.upper() == "NO" else "BUY_YES",
            action=action,
            status=status,
            reason_code=reason_code,
            reason_es=reason_es,
            reason_en=reason_en,
            market_probability=edge.market_probability,
            model_probability=probability.probability,
            raw_edge=edge.raw_edge,
            net_edge=edge.net_edge,
            confidence=probability.confidence_score,
            executable_price=edge.executable_price,
            max_recommended_price=edge.executable_price,
            best_bid=orderbook.best_bid,
            best_ask=orderbook.best_ask,
            spread=orderbook.spread,
            liquidity_usd=liquidity_usd,
            fee_rate=fee_schedule.rate if fee_schedule else None,
            estimated_fees=edge.estimated_fees,
            spread_cost=edge.spread_cost,
            slippage=edge.slippage,
            uncertainty_penalty=edge.uncertainty_penalty,
            safety_margin=edge.safety_margin,
            gross_ev=edge.gross_ev,
            net_ev=edge.net_ev,
            recommended_stake=risk.recommended_stake,
            maximum_allowed_stake=risk.maximum_allowed_stake,
            resolution_source=market.resolution_source,
            resolution_station=market.resolution_station,
            resolution_rules=market.resolution_rules,
            polymarket_url=market.polymarket_url,
            distribution_json=json.dumps(probability.distribution),
            forecasts_json=json.dumps([f.raw for f in bundle.forecasts], default=str),
            observation_json=json.dumps(observation.raw if observation else {}, default=str),
            risks_json=json.dumps(risk.details),
            data_freshness_json=json.dumps(
                {
                    "market_data": orderbook.timestamp_utc.isoformat(),
                    "weather_forecast": bundle.fetched_at_utc.isoformat(),
                    "observation": observation.fetched_at_utc.isoformat() if observation else None,
                }
            ),
            created_at_utc=utc_now(),
        )
        session.add(signal)
        session.flush()
        return signal

    def _official_source_guard(
        self,
        market: ParsedWeatherMarket,
        outcome: ParsedOutcome,
        observation: ObservationSnapshot | None,
    ) -> tuple[str, str, str] | None:
        if not self.app_settings.kalshi_require_official_weather_source:
            return None
        if not market.market_id.startswith("KALSHI:") or "Weather Company" not in market.resolution_rules:
            return None
        if observation is None or observation.provider != "the-weather-company-kalshi":
            return (
                "OFFICIAL_SOURCE_UNAVAILABLE",
                "La fuente oficial de Kalshi/The Weather Company no está disponible. Señal bloqueada.",
                "Kalshi/The Weather Company official source is unavailable. Signal blocked.",
            )
        raw = observation.raw if isinstance(observation.raw, dict) else {}
        if raw.get("source") == "hourly_metar" and not raw.get("local_day_complete"):
            return (
                "OFFICIAL_DAY_INCOMPLETE",
                "La fuente oficial todavía no tiene el día completo confirmado. Señal bloqueada.",
                "The official source does not have the complete day confirmed yet. Signal blocked.",
            )
        reference = observation.observed_max if market.weather_metric == "daily_max" else observation.observed_min
        boundaries = [value for value in (outcome.lower_bound, outcome.upper_bound) if value is not None]
        if reference is None or not boundaries:
            return (
                "OFFICIAL_OBSERVATION_INCOMPLETE",
                "La fuente oficial no trae una máxima/mínima usable para este outcome. Señal bloqueada.",
                "The official source does not provide a usable max/min observation for this outcome. Signal blocked.",
            )
        min_distance = min(abs(reference - boundary) for boundary in boundaries)
        min_margin = self.app_settings.kalshi_min_source_margin_f
        if market.unit.upper() == "C":
            min_margin = min_margin * 5.0 / 9.0
        if min_distance < min_margin:
            return (
                "SOURCE_MARGIN_TOO_THIN",
                (
                    f"Lectura oficial/preliminar {reference:.1f}{market.unit} a solo "
                    f"{min_distance:.1f}{market.unit} del strike. Señal bloqueada por margen mínimo."
                ),
                (
                    f"Official/preliminary reading {reference:.1f}{market.unit} is only "
                    f"{min_distance:.1f}{market.unit} from the strike. Signal blocked by minimum margin."
                ),
            )
        return None

    def _reason(self, edge_code: str, liquidity: Any, risk: Any, runtime: RuntimeSettings) -> tuple[str, str, str]:
        if runtime.kill_switch:
            return "KILL_SWITCH", "Kill switch activo.", "Kill switch is active."
        if runtime.paused:
            return "PAUSED", "Bot pausado.", "Bot is paused."
        if not liquidity.ok:
            return liquidity.reason_code, liquidity.reason_es, liquidity.reason_en
        if edge_code != "EDGE_OK":
            return edge_code, "Edge neto menor al umbral después de costes.", "Net edge is below threshold after costs."
        if not risk.approved:
            return risk.reason_code, risk.reason_es, risk.reason_en
        return "EDGE_OK", "Oportunidad aprobada.", "Opportunity approved."

    def _action_for(self, mode: str, outcome: ParsedOutcome, actionable: bool) -> str:
        if not actionable:
            return "NO_TRADE"
        side = "BUY_NO" if outcome.side.upper() == "NO" else "BUY_YES"
        if mode == "OBSERVE":
            return "WATCH"
        return side


def deterministic_explanation(market_probability: float, model_probability: float, net_edge: float, outcome: str) -> tuple[str, str]:
    market_pct = market_probability * 100
    model_pct = model_probability * 100
    edge_pts = net_edge * 100
    es = (
        f"El mercado asigna {market_pct:.1f}% a {outcome}. "
        f"Nuestro modelo estima {model_pct:.1f}%. "
        f"Después de spread, fees e incertidumbre, el edge neto estimado es {edge_pts:+.1f} puntos porcentuales."
    )
    en = (
        f"The market assigns {market_pct:.1f}% to {outcome}. "
        f"Our model estimates {model_pct:.1f}%. "
        f"After spread, fees, and uncertainty, estimated net edge is {edge_pts:+.1f} percentage points."
    )
    return es, en


def _hours_to_resolution(market: ParsedWeatherMarket) -> float:
    return max(0.0, _signed_hours_to_resolution(market))


def _signed_hours_to_resolution(market: ParsedWeatherMarket) -> float:
    from datetime import datetime, time
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(market.timezone)
    target_end = datetime.combine(market.target_date, time.max, tzinfo=tz)
    return (target_end.astimezone(utc_now().tzinfo) - utc_now()).total_seconds() / 3600.0


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
