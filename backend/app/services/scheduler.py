from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.db.session import session_scope
from app.services.crypto_scanner import CryptoScannerService
from app.services.scanner import ScannerService
from app.services.settings_service import SettingsService


logger = logging.getLogger(__name__)


class ScannerScheduler:
    def __init__(self, scanner: ScannerService, settings_service: SettingsService, crypto_scanner: CryptoScannerService | None = None) -> None:
        self.scanner = scanner
        self.settings_service = settings_service
        self.crypto_scanner = crypto_scanner
        self.scheduler = AsyncIOScheduler(timezone="UTC")

    def start(self) -> None:
        if self.scheduler.running:
            return
        interval = self._interval()
        self.scheduler.add_job(
            self.scanner.run_once,
            trigger=IntervalTrigger(minutes=interval),
            id="weatheredgeflow-scan",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        if self.crypto_scanner is not None:
            self.scheduler.add_job(
                self.crypto_scanner.run_once,
                trigger=IntervalTrigger(minutes=interval),
                id="weatheredgeflow-crypto-scan",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
        self.scheduler.start()

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def reschedule(self) -> None:
        if not self.scheduler.running:
            return
        interval = self._interval()
        self.scheduler.reschedule_job("weatheredgeflow-scan", trigger=IntervalTrigger(minutes=interval))
        if self.scheduler.get_job("weatheredgeflow-crypto-scan"):
            self.scheduler.reschedule_job("weatheredgeflow-crypto-scan", trigger=IntervalTrigger(minutes=interval))

    def status(self) -> dict[str, object]:
        job = self.scheduler.get_job("weatheredgeflow-scan") if self.scheduler.running else None
        crypto_job = self.scheduler.get_job("weatheredgeflow-crypto-scan") if self.scheduler.running else None
        return {
            "running": self.scheduler.running,
            "next_run_time": job.next_run_time.isoformat() if job and job.next_run_time else None,
            "crypto_next_run_time": crypto_job.next_run_time.isoformat() if crypto_job and crypto_job.next_run_time else None,
            "scan_running": self.scanner._lock.locked(),
        }

    def _interval(self) -> int:
        with session_scope() as session:
            runtime = self.settings_service.get_runtime(session)
            return max(1, runtime.scan_interval_minutes)
