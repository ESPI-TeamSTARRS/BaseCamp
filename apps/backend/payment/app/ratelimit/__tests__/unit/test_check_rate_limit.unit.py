from datetime import UTC, datetime, timedelta

import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events import service_event_names as names
from app.core.events.outcome import Outcome
from app.ratelimit.application.check_rate_limit import CheckRateLimitUseCase
from app.ratelimit.application.exceptions.rate_limit_exceeded_error import RateLimitExceededError
from app.ratelimit.domain.interfaces.rate_limit_counter import RateLimitCounter

T0 = datetime(2026, 10, 20, 12, 0, 10, tzinfo=UTC)  # 10 s après le début de la fenêtre


class FakeCounter(RateLimitCounter):
    """Compteur partagé simulé : l'état est dans l'objet, pas dans le cas d'usage."""

    def __init__(self) -> None:
        self.hits: dict[tuple[str, str, datetime], int] = {}
        self.purged: list[tuple[str, str, datetime]] = []

    def hit(self, caller: str, route: str, window_start: datetime) -> int:
        key = (caller, route, window_start)
        self.hits[key] = self.hits.get(key, 0) + 1
        return self.hits[key]

    def purge_before(self, caller: str, route: str, before: datetime) -> None:
        self.purged.append((caller, route, before))


def _use_case(
    counter: FakeCounter,
    now: datetime = T0,
    limits: dict[str, int] | None = None,
    events: InMemoryBusinessEventLogger | None = None,
) -> CheckRateLimitUseCase:
    return CheckRateLimitUseCase(
        counter,
        lambda: now,
        60,
        limits or {"intents.create": 3},
        events or InMemoryBusinessEventLogger(),
    )


class TestCheckRateLimit:
    def test_requests_within_the_limit_are_allowed(self) -> None:
        use_case = _use_case(FakeCounter())

        for _ in range(3):
            use_case.execute("shop", "intents.create")

    def test_request_above_the_limit_raises_with_the_time_left_in_the_window(self) -> None:
        use_case = _use_case(FakeCounter())
        for _ in range(3):
            use_case.execute("shop", "intents.create")

        with pytest.raises(RateLimitExceededError) as error:
            use_case.execute("shop", "intents.create")

        assert error.value.retry_after_seconds == 50

    def test_another_caller_or_route_has_its_own_budget(self) -> None:
        use_case = _use_case(FakeCounter(), limits={"intents.create": 1, "intents.read": 1})
        use_case.execute("shop", "intents.create")

        use_case.execute("admin", "intents.create")
        use_case.execute("shop", "intents.read")
        with pytest.raises(RateLimitExceededError):
            use_case.execute("shop", "intents.create")

    def test_a_new_window_resets_the_budget(self) -> None:
        counter = FakeCounter()
        for _ in range(3):
            _use_case(counter).execute("shop", "intents.create")

        _use_case(counter, T0 + timedelta(seconds=60)).execute("shop", "intents.create")

    def test_two_instances_sharing_the_counter_share_the_budget(self) -> None:
        counter = FakeCounter()
        first, second = _use_case(counter), _use_case(counter)
        first.execute("shop", "intents.create")
        second.execute("shop", "intents.create")
        first.execute("shop", "intents.create")

        with pytest.raises(RateLimitExceededError):
            second.execute("shop", "intents.create")

    def test_old_windows_are_purged_when_a_window_opens(self) -> None:
        counter = FakeCounter()

        _use_case(counter).execute("shop", "intents.create")

        window_start = datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)
        assert counter.purged == [("shop", "intents.create", window_start - timedelta(seconds=60))]

    def test_a_route_without_configured_limit_is_a_programming_error(self) -> None:
        with pytest.raises(KeyError):
            _use_case(FakeCounter()).execute("shop", "unknown")


class TestRateLimitEvents:
    def test_a_refusal_emits_a_denied_event_without_any_secret(self) -> None:
        events = InMemoryBusinessEventLogger()
        use_case = _use_case(FakeCounter(), limits={"intents.create": 1}, events=events)
        use_case.execute("shop", "intents.create")
        assert events.events == []  # le succès n'émet rien : pas de bruit à chaque requête

        with pytest.raises(RateLimitExceededError):
            use_case.execute("shop", "intents.create")

        (event,) = events.events
        assert (event.event, event.outcome, event.reason) == (
            names.RATE_LIMITED,
            Outcome.DENIED,
            "rate_limit_exceeded",
        )
        assert (event.actor_type, event.actor_id) == ("service", "shop")
        assert (event.resource_type, event.resource_id) == ("route", "intents.create")
        assert event.attributes == {"retry_after_seconds": 50}
