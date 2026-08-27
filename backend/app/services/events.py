from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import SystemEvent
from app.utils.time import utc_now


def log_event(
    session: Session,
    *,
    message_es: str,
    message_en: str,
    level: str = "INFO",
    category: str = "SCANNER",
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        SystemEvent(
            timestamp_utc=utc_now(),
            level=level,
            category=category,
            message_es=message_es,
            message_en=message_en,
            details_json=json.dumps(details or {}),
        )
    )
    session.flush()

