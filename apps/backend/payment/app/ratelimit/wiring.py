from datetime import UTC, datetime

from sqlalchemy import Engine

from app.core.config import Settings
from app.core.events.business_event_logger import BusinessEventLogger
from app.ratelimit.application.check_rate_limit import CheckRateLimitUseCase
from app.ratelimit.application.rate_limit_routes import ROUTE_INTENTS_CREATE, ROUTE_INTENTS_READ
from app.ratelimit.infrastructure.repositories.sqlalchemy_rate_limit_counter import (
    SqlAlchemyRateLimitCounter,
)


def build_rate_limiter(
    engine: Engine, settings: Settings, events: BusinessEventLogger
) -> CheckRateLimitUseCase:
    """Assemble la limitation de débit avec ses compteurs partagés en base."""
    return CheckRateLimitUseCase(
        SqlAlchemyRateLimitCounter(engine),
        lambda: datetime.now(UTC),
        settings.rate_limit_window_seconds,
        {
            ROUTE_INTENTS_CREATE: settings.rate_limit_create_per_window,
            ROUTE_INTENTS_READ: settings.rate_limit_read_per_window,
        },
        events,
    )
