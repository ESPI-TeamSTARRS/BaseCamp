from datetime import UTC, datetime

from app.customer_identity.domain.interfaces.clock import Clock


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(UTC)
