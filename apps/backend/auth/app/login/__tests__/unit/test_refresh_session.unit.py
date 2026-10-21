from datetime import timedelta

import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.login.__tests__.fakes import (
    FakeAccessTokenSigner,
    FakeClock,
    FakeRefreshTokenGenerator,
    FakeStore,
    FakeUnitOfWork,
    make_account,
)
from app.login.application.invalid_refresh_token_error import InvalidRefreshTokenError
from app.login.application.refresh_session import RefreshSessionUseCase
from app.login.domain.entities.account import Account
from app.login.domain.entities.refresh_token import RefreshToken

ACCESS_TTL = 900
REFRESH_TTL = 604800
OLD = "raw-old-token"


class CountingGenerator(FakeRefreshTokenGenerator):
    """Un jeton neuf a chaque appel, comme le vrai generateur."""

    def __init__(self) -> None:
        self.count = 0

    def generate(self) -> str:
        self.count += 1
        return f"raw-next-token-{self.count}"


class Setup:
    def __init__(self, account: Account | None = None, seed: bool = True) -> None:
        self.account = account or make_account()
        self.store = FakeStore(self.account)
        self.clock = FakeClock()
        self.events = InMemoryBusinessEventLogger()
        self.signer = FakeAccessTokenSigner()
        self.tokens = CountingGenerator()
        self.use_case = RefreshSessionUseCase(
            lambda: FakeUnitOfWork(self.store),
            self.signer,
            self.tokens,
            self.clock,
            self.events,
            ACCESS_TTL,
            REFRESH_TTL,
        )
        self.first: RefreshToken | None = None
        if seed:
            self.first = RefreshToken.issue(
                self.account.id, self.tokens.digest(OLD), self.clock.now(), REFRESH_TTL
            )
            self.store.refresh_tokens.append(self.first)


class TestRotation:
    def test_a_valid_token_yields_a_new_access_token_and_a_new_refresh_token(self) -> None:
        setup = Setup()

        result = setup.use_case.execute(OLD)

        assert result.access_token == f"signed::{setup.account.id}"
        assert result.expires_in == ACCESS_TTL
        assert result.refresh_token == "raw-next-token-1"
        assert result.refresh_expires_in == REFRESH_TTL

    def test_the_old_token_is_consumed_and_the_new_one_joins_the_same_family(self) -> None:
        setup = Setup()
        assert setup.first is not None

        setup.use_case.execute(OLD)

        old, new = setup.store.refresh_tokens
        assert old.used_at == setup.clock.now()
        assert new.used_at is None
        assert new.family_id == setup.first.family_id
        assert new.token_hash == setup.tokens.digest("raw-next-token-1")

    def test_the_new_token_gets_a_fresh_seven_day_lifetime(self) -> None:
        setup = Setup()
        setup.clock.current += timedelta(days=3)

        setup.use_case.execute(OLD)

        assert setup.store.refresh_tokens[-1].expires_at == setup.clock.now() + timedelta(
            seconds=REFRESH_TTL
        )

    def test_the_chain_can_continue_with_the_new_token(self) -> None:
        setup = Setup()
        first = setup.use_case.execute(OLD)

        second = setup.use_case.execute(first.refresh_token)

        assert second.refresh_token == "raw-next-token-2"
        assert len(setup.store.refresh_tokens) == 3

    def test_it_emits_a_success_event_without_any_token(self) -> None:
        setup = Setup()

        result = setup.use_case.execute(OLD, "203.0.113.7")

        [event] = setup.events.events
        assert (event.event, event.outcome) == ("auth.token_refreshed", Outcome.SUCCESS)
        assert event.resource_id == str(setup.account.id)
        assert event.client_ip == "203.0.113.7"
        assert OLD not in repr(event)
        assert result.refresh_token not in repr(event)


class TestReuse:
    def test_a_replayed_token_revokes_the_whole_family(self) -> None:
        setup = Setup()
        successor = setup.use_case.execute(OLD)

        with pytest.raises(InvalidRefreshTokenError):
            setup.use_case.execute(OLD)

        assert setup.store.refresh_tokens == []
        with pytest.raises(InvalidRefreshTokenError):
            setup.use_case.execute(successor.refresh_token)

    def test_a_replay_is_logged_as_reuse_detected(self) -> None:
        setup = Setup()
        setup.use_case.execute(OLD)
        setup.events.events.clear()

        with pytest.raises(InvalidRefreshTokenError):
            setup.use_case.execute(OLD, "203.0.113.7")

        [event] = setup.events.events
        assert (event.event, event.outcome, event.reason) == (
            "auth.refresh_reuse_detected",
            Outcome.DENIED,
            "refresh_token_reused",
        )
        assert event.resource_id == str(setup.account.id)
        assert event.client_ip == "203.0.113.7"
        assert OLD not in repr(event)

    def test_other_families_of_the_account_are_left_alone(self) -> None:
        setup = Setup()
        other = RefreshToken.issue(setup.account.id, "other-digest", setup.clock.now(), REFRESH_TTL)
        setup.store.refresh_tokens.append(other)
        setup.use_case.execute(OLD)

        with pytest.raises(InvalidRefreshTokenError):
            setup.use_case.execute(OLD)

        assert setup.store.refresh_tokens == [other]


class TestRejection:
    def test_an_unknown_token_is_refused_and_logged_with_its_cause(self) -> None:
        setup = Setup()

        with pytest.raises(InvalidRefreshTokenError) as error:
            setup.use_case.execute("never-issued")

        assert error.value.message == "Session expirée."
        [event] = setup.events.events
        assert (event.event, event.outcome, event.reason) == (
            "auth.refresh_rejected",
            Outcome.DENIED,
            "invalid_refresh_token",
        )
        assert dict(event.attributes) == {"cause": "unknown_token", "account_id": None}
        assert "never-issued" not in repr(event)

    def test_an_empty_token_is_refused_like_an_unknown_one(self) -> None:
        setup = Setup()

        with pytest.raises(InvalidRefreshTokenError):
            setup.use_case.execute("")

    def test_an_expired_token_is_refused_without_revoking_anything(self) -> None:
        setup = Setup()
        setup.clock.current += timedelta(seconds=REFRESH_TTL)

        with pytest.raises(InvalidRefreshTokenError):
            setup.use_case.execute(OLD)

        [event] = setup.events.events
        assert event.event == "auth.refresh_rejected"
        assert dict(event.attributes)["cause"] == "expired_token"
        assert len(setup.store.refresh_tokens) == 1

    def test_a_replayed_token_after_its_expiry_is_only_expired(self) -> None:
        setup = Setup()
        setup.use_case.execute(OLD)
        setup.clock.current += timedelta(seconds=REFRESH_TTL)
        setup.events.events.clear()

        with pytest.raises(InvalidRefreshTokenError):
            setup.use_case.execute(OLD)

        [event] = setup.events.events
        assert event.event == "auth.refresh_rejected"

    def test_a_disabled_account_loses_its_sessions(self) -> None:
        setup = Setup(make_account(disabled=True))

        with pytest.raises(InvalidRefreshTokenError):
            setup.use_case.execute(OLD)

        assert setup.store.refresh_tokens == []
        [event] = setup.events.events
        assert dict(event.attributes)["cause"] == "account_disabled"

    def test_a_token_of_a_vanished_account_is_refused(self) -> None:
        setup = Setup()
        del setup.store.accounts[setup.account.id]

        with pytest.raises(InvalidRefreshTokenError):
            setup.use_case.execute(OLD)

        assert setup.store.refresh_tokens == []
