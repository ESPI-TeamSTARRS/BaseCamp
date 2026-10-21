from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TextIO

import structlog

from app.core.events.business_event import BusinessEvent
from app.core.events.outcome import Outcome
from app.core.logging.correlation import current_correlation_id
from app.core.logging.event_sanitizer import EventSanitizer

_LEVEL_BY_OUTCOME = {
    Outcome.SUCCESS: "info",
    Outcome.DENIED: "warning",
    Outcome.ERROR: "error",
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


class StructlogBusinessEventLogger:
    """Ecrit chaque evenement metier en une ligne JSON (schema docs/development/log-event.schema.json)."""

    def __init__(
        self,
        service: str,
        stream: TextIO,
        clock: Callable[[], datetime] = _utc_now,
        sanitizer: EventSanitizer | None = None,
    ) -> None:
        self._service = service
        self._clock = clock
        self._sanitizer = sanitizer or EventSanitizer()
        self._logger = structlog.wrap_logger(
            structlog.PrintLogger(file=stream),
            processors=[structlog.processors.JSONRenderer()],
        )

    def log(self, event: BusinessEvent) -> None:
        record = self._record(event)
        getattr(self._logger, record["level"])(**record)

    def _record(self, event: BusinessEvent) -> dict[str, Any]:
        timestamp = self._clock().astimezone(UTC).isoformat(timespec="milliseconds")
        record: dict[str, Any] = {
            "timestamp": timestamp.replace("+00:00", "Z"),
            "service": self._service,
            "level": _LEVEL_BY_OUTCOME[event.outcome],
            "event": event.event,
            "correlation_id": current_correlation_id(),
            "outcome": event.outcome.value,
        }
        optional = {
            "reason": event.reason,
            "resource_type": event.resource_type,
            "resource_id": self._clean(event.resource_id),
            "actor_type": event.actor_type,
            "actor_id": self._clean(event.actor_id),
            "duration_ms": event.duration_ms,
            "client_ip": event.client_ip,
        }
        record.update({key: value for key, value in optional.items() if value is not None})
        if event.attributes:
            record["attributes"] = self._sanitizer.attributes(event.attributes)
        return record

    def _clean(self, value: str | None) -> str | None:
        return None if value is None else self._sanitizer.text(value)
