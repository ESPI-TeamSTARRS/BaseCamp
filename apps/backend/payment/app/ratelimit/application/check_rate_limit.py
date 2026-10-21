import math
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta

from app.core.events import service_event_names as names
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.ratelimit.application.exceptions.rate_limit_exceeded_error import RateLimitExceededError
from app.ratelimit.domain.interfaces.rate_limit_counter import RateLimitCounter


class CheckRateLimitUseCase:
    """Limitation de débit à fenêtre fixe, par appelant et par route.

    Les compteurs vivent en base (via `RateLimitCounter`) : toutes les instances du service
    partagent donc le même budget, sans aucun état en mémoire.
    """

    def __init__(
        self,
        counter: RateLimitCounter,
        clock: Callable[[], datetime],
        window_seconds: int,
        limits_by_route: Mapping[str, int],
        events: BusinessEventLogger,
    ) -> None:
        self._counter = counter
        self._clock = clock
        self._window_seconds = window_seconds
        self._limits_by_route = limits_by_route
        self._events = events

    def execute(self, caller: str, route: str) -> None:
        limit = self._limits_by_route[route]
        now = self._clock()
        window_start = self._window_start(now)
        count = self._counter.hit(caller, route, window_start)
        if count == 1:
            self._counter.purge_before(
                caller, route, window_start - timedelta(seconds=self._window_seconds)
            )
        if count > limit:
            window_end = window_start + timedelta(seconds=self._window_seconds)
            retry_after = max(1, math.ceil((window_end - now).total_seconds()))
            self._events.log(
                BusinessEvent.denied(
                    names.RATE_LIMITED,
                    "rate_limit_exceeded",
                    resource_type="route",
                    resource_id=route,
                    actor_type="service",
                    actor_id=caller,
                    attributes={"retry_after_seconds": retry_after},
                )
            )
            raise RateLimitExceededError(retry_after)

    def _window_start(self, now: datetime) -> datetime:
        seconds = int(now.timestamp()) // self._window_seconds * self._window_seconds
        return datetime.fromtimestamp(seconds, tz=UTC)
