from datetime import UTC, datetime

from app.service_token.domain.interfaces.clock import Clock


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(UTC)
