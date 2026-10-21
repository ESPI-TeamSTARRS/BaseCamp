from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.login.__tests__.fakes import (
    FakeClock,
    FakeRefreshTokenGenerator,
    FakeStore,
    FakeUnitOfWork,
    make_account,
)
from app.login.application.logout_session import LogoutSessionUseCase
from app.login.domain.entities.refresh_token import RefreshToken

TTL = 604800


class Setup:
    def __init__(self) -> None:
        self.account = make_account()
        self.store = FakeStore(self.account)
        self.tokens = FakeRefreshTokenGenerator()
        self.events = InMemoryBusinessEventLogger()
        self.use_case = LogoutSessionUseCase(
            lambda: FakeUnitOfWork(self.store), self.tokens, self.events
        )
        self.clock = FakeClock()

    def add_session(self, raw: str) -> RefreshToken:
        token = RefreshToken.issue(self.account.id, self.tokens.digest(raw), self.clock.now(), TTL)
        self.store.refresh_tokens.append(token)
        return token


class TestLogout:
    def test_it_revokes_the_family_of_the_presented_token(self) -> None:
        setup = Setup()
        first = setup.add_session("raw-a")
        setup.store.refresh_tokens.append(
            first.successor("digest-b", setup.clock.now(), TTL).consumed(setup.clock.now())
        )
        other = setup.add_session("raw-other")

        setup.use_case.execute("raw-a", "203.0.113.7")

        assert setup.store.refresh_tokens == [other]

    def test_it_emits_a_success_event_without_the_token(self) -> None:
        setup = Setup()
        setup.add_session("raw-a")

        setup.use_case.execute("raw-a", "203.0.113.7")

        [event] = setup.events.events
        assert (event.event, event.outcome) == ("auth.logout_completed", Outcome.SUCCESS)
        assert event.resource_id == str(setup.account.id)
        assert dict(event.attributes) == {"sessions_revoked": 1}
        assert "raw-a" not in repr(event)

    def test_it_is_idempotent(self) -> None:
        setup = Setup()
        setup.add_session("raw-a")
        setup.use_case.execute("raw-a")
        setup.events.events.clear()

        setup.use_case.execute("raw-a")

        assert setup.store.refresh_tokens == []
        assert setup.events.events == []

    def test_an_absent_or_unknown_token_does_nothing(self) -> None:
        setup = Setup()
        kept = setup.add_session("raw-a")

        setup.use_case.execute(None)
        setup.use_case.execute("")
        setup.use_case.execute("never-issued")

        assert setup.store.refresh_tokens == [kept]
        assert setup.events.events == []
