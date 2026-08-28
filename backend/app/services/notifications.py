from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Any

from sqlalchemy.orm import Session

from app.config import AppSettings
from app.db.models import CryptoSignal, NotificationEvent, Signal
from app.services.events import log_event
from app.services.settings_service import RuntimeSettings
from app.utils.time import utc_now


logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, app_settings: AppSettings) -> None:
        self.app_settings = app_settings

    def maybe_notify_weather_signal(self, session: Session, signal: Signal, runtime: RuntimeSettings) -> bool:
        if signal.status != "OPPORTUNITY":
            return False
        probability = float(signal.model_probability or 0.0)
        net_edge = float(signal.net_edge or 0.0)
        price = float(signal.executable_price or 0.0)
        confidence = float(signal.confidence or 0.0)
        if not self._passes_thresholds(runtime, probability, net_edge, price, confidence):
            return False
        subject = f"WeatherEdgeflow ALERTA: {signal.action} {signal.outcome}"
        body = "\n".join(
            [
                "WeatherEdgeflow detecto una oportunidad aprobada.",
                "",
                f"Mercado: {signal.question}",
                f"Accion: {signal.action}",
                f"Outcome: {signal.outcome}",
                f"Precio maximo: {_fmt_pct(price)}",
                f"Probabilidad modelo: {_fmt_pct(probability)}",
                f"Edge neto: {_fmt_pp(net_edge)}",
                f"Confidence: {confidence:.1f}/100",
                f"Stake recomendado: ${float(signal.recommended_stake or 0.0):.2f}",
                f"URL: {signal.polymarket_url or '-'}",
                "",
                "No es orden automatica. Revisar y ejecutar manualmente si decidis tomarla.",
            ]
        )
        return self._record_and_send(
            session,
            runtime=runtime,
            dedupe_key=f"weather:{signal.market_id}:{signal.token_id}:{signal.action}:{signal.target_date}",
            signal_type="WEATHER",
            signal_id=signal.id,
            subject=subject,
            body=body,
        )

    def maybe_notify_crypto_signal(self, session: Session, signal: CryptoSignal, runtime: RuntimeSettings) -> bool:
        if signal.status != "OPPORTUNITY":
            return False
        probability_yes = float(signal.model_probability or 0.0)
        selected_probability = 1.0 - probability_yes if signal.action == "BUY_NO" else probability_yes
        net_edge = float(signal.net_daily_edge or 0.0)
        price = float(signal.market_probability or 0.0)
        confidence = float(signal.confidence or 0.0)
        if not self._passes_thresholds(runtime, selected_probability, net_edge, price, confidence):
            return False
        subject = f"WeatherEdgeflow ALERTA crypto: {signal.action} {signal.symbol}"
        body = "\n".join(
            [
                "WeatherEdgeflow detecto una oportunidad crypto aprobada.",
                "",
                f"Venue: {signal.venue}",
                f"Simbolo: {signal.symbol}",
                f"Estrategia: {signal.strategy}",
                f"Accion: {signal.action}",
                f"Precio maximo: {_fmt_pct(price)}",
                f"Probabilidad modelo de la accion: {_fmt_pct(selected_probability)}",
                f"Edge neto: {_fmt_pp(net_edge)}",
                f"Confidence: {confidence:.1f}/100",
                "",
                "No es orden automatica. Revisar y ejecutar manualmente si decidis tomarla.",
            ]
        )
        return self._record_and_send(
            session,
            runtime=runtime,
            dedupe_key=f"crypto:{signal.venue}:{signal.symbol}:{signal.strategy}:{signal.action}:{signal.raw_json[:80]}",
            signal_type="CRYPTO",
            signal_id=signal.id,
            subject=subject,
            body=body,
        )

    def _passes_thresholds(self, runtime: RuntimeSettings, probability: float, net_edge: float, price: float, confidence: float) -> bool:
        if runtime.paused or runtime.kill_switch:
            return False
        if not runtime.alert_email_enabled or not runtime.alert_email_recipient:
            return False
        if confidence < runtime.alert_min_confidence:
            return False
        if probability < runtime.alert_min_model_probability:
            return False
        if net_edge < runtime.alert_min_net_edge:
            return False
        if price <= 0 or price >= 1:
            return False
        profit_per_1 = (1.0 / price) - 1.0
        return profit_per_1 >= runtime.alert_min_profit_usd_per_1

    def _record_and_send(
        self,
        session: Session,
        *,
        runtime: RuntimeSettings,
        dedupe_key: str,
        signal_type: str,
        signal_id: int,
        subject: str,
        body: str,
    ) -> bool:
        if session.query(NotificationEvent).filter(NotificationEvent.dedupe_key == dedupe_key[:256]).first() is not None:
            return False
        event = NotificationEvent(
            dedupe_key=dedupe_key[:256],
            signal_type=signal_type,
            signal_id=signal_id,
            recipient=runtime.alert_email_recipient,
            subject=subject,
            status="PENDING",
            created_at_utc=utc_now(),
        )
        session.add(event)
        session.flush()

        if not self._smtp_ready():
            event.status = "SKIPPED"
            event.error = "SMTP_NOT_CONFIGURED"
            log_event(
                session,
                message_es=f"Alerta email omitida: SMTP no configurado para {runtime.alert_email_recipient}",
                message_en=f"Email alert skipped: SMTP not configured for {runtime.alert_email_recipient}",
                category="NOTIFICATION",
                level="WARNING",
                details={"signal_type": signal_type, "signal_id": signal_id},
            )
            return False

        try:
            self._send_email(runtime.alert_email_recipient, subject, body)
        except Exception as exc:  # noqa: BLE001
            logger.exception("email alert failed")
            event.status = "FAILED"
            event.error = str(exc)
            log_event(
                session,
                message_es=f"Error enviando alerta email: {exc}",
                message_en=f"Email alert failed: {exc}",
                category="NOTIFICATION",
                level="ERROR",
                details={"signal_type": signal_type, "signal_id": signal_id},
            )
            return False

        event.status = "SENT"
        event.sent_at_utc = utc_now()
        log_event(
            session,
            message_es=f"Alerta email enviada a {runtime.alert_email_recipient}",
            message_en=f"Email alert sent to {runtime.alert_email_recipient}",
            category="NOTIFICATION",
            details={"signal_type": signal_type, "signal_id": signal_id},
        )
        return True

    def _smtp_ready(self) -> bool:
        return bool(self.app_settings.smtp_host and self.app_settings.smtp_username and self.app_settings.smtp_password)

    def _send_email(self, recipient: str, subject: str, body: str) -> None:
        sender = self.app_settings.smtp_from_email or self.app_settings.smtp_username
        message = EmailMessage()
        message["From"] = sender
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        with smtplib.SMTP(self.app_settings.smtp_host, self.app_settings.smtp_port, timeout=20) as smtp:
            if self.app_settings.smtp_use_tls:
                smtp.starttls()
            smtp.login(self.app_settings.smtp_username, self.app_settings.smtp_password)
            smtp.send_message(message)


def _fmt_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _fmt_pp(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value * 100:.1f} pp"
