from datetime import timedelta

import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.lockout.__tests__.fakes import FIVE_IN_FIFTEEN, FakeLockoutUnitOfWork, LockoutStore
from app.lockout.application.lockout_service import LockoutService
from app.login.__tests__.fakes import (
    ACCOUNT_SECRET,
    EMAIL,
    FakeAccessTokenSigner,
    FakeClock,
    FakeEmailFingerprinter,
    FakePasswordVerifier,
    FakeRefreshTokenGenerator,
    FakeStore,
    FakeUnitOfWork,
    make_account,
)
from app.login.application.invalid_credentials_error import InvalidCredentialsError
from app.login.application.login_account import LoginAccountUseCase
from app.login.domain.entities.account import Account

WRONG = "mauvais-mot-de-passe"


class Setup:
    def __init__(self, account: Account) -> None:
        self.store = FakeStore(account)
        self.verifier = FakePasswordVerifier()
        self.clock = FakeClock()
        self.events = InMemoryBusinessEventLogger()
        self.lockouts = LockoutStore()
        self.use_case = LoginAccountUseCase(
            lambda: FakeUnitOfWork(self.store),
            self.verifier,
            FakeAccessTokenSigner(),
            FakeRefreshTokenGenerator(),
            self.clock,
            self.events,
            FakeEmailFingerprinter(),
            LockoutService(
                lambda: FakeLockoutUnitOfWork(self.lockouts), FIVE_IN_FIFTEEN, self.events
            ),
            900,
            604800,
        )


def fail(setup: Setup, times: int, email: str = EMAIL) -> None:
    for _ in range(times):
        with pytest.raises(InvalidCredentialsError):
            setup.use_case.execute(email, WRONG)
        setup.clock.current += timedelta(seconds=10)


class TestLockout:
    def test_four_failures_do_not_prevent_a_valid_login(self) -> None:
        setup = Setup(make_account())
        fail(setup, 4)

        assert setup.use_case.execute(EMAIL, ACCOUNT_SECRET).access_token

    def test_five_failures_lock_even_the_right_password(self) -> None:
        setup = Setup(make_account())
        fail(setup, 5)

        with pytest.raises(InvalidCredentialsError) as raised:
            setup.use_case.execute(EMAIL, ACCOUNT_SECRET)

        assert raised.value.message == "Identifiants invalides."
        assert setup.store.refresh_tokens == []

    def test_an_unknown_address_is_locked_exactly_like_a_known_one(self) -> None:
        setup = Setup(make_account())
        fail(setup, 5, email="inconnu@example.com")

        with pytest.raises(InvalidCredentialsError) as raised:
            setup.use_case.execute("inconnu@example.com", ACCOUNT_SECRET)

        assert raised.value.message == "Identifiants invalides."
        assert [e.reason for e in setup.events.events if e.event == "auth.login_failed"] == [
            "invalid_credentials"
        ] * 6

    def test_a_locked_attempt_costs_one_argon2_verification_like_any_failure(self) -> None:
        setup = Setup(make_account())
        fail(setup, 5)
        before = setup.verifier.verifications + setup.verifier.decoys

        with pytest.raises(InvalidCredentialsError):
            setup.use_case.execute(EMAIL, ACCOUNT_SECRET)

        assert setup.verifier.verifications + setup.verifier.decoys == before + 1

    def test_the_lock_ends_after_fifteen_minutes(self) -> None:
        setup = Setup(make_account())
        fail(setup, 5)
        setup.clock.current += timedelta(minutes=16)

        assert setup.use_case.execute(EMAIL, ACCOUNT_SECRET).access_token

    def test_a_success_resets_the_counter(self) -> None:
        setup = Setup(make_account())
        fail(setup, 4)
        setup.use_case.execute(EMAIL, ACCOUNT_SECRET)

        fail(setup, 4)

        assert setup.use_case.execute(EMAIL, ACCOUNT_SECRET).access_token

    def test_attempts_during_the_lock_do_not_extend_it(self) -> None:
        setup = Setup(make_account())
        fail(setup, 5)
        for _ in range(20):
            with pytest.raises(InvalidCredentialsError):
                setup.use_case.execute(EMAIL, WRONG)
        setup.clock.current += timedelta(minutes=16)

        assert setup.use_case.execute(EMAIL, ACCOUNT_SECRET).access_token

    def test_a_disabled_account_counts_like_any_other_failure(self) -> None:
        setup = Setup(make_account(disabled=True))

        fail(setup, 5)

        locked = setup.lockouts.rows[("password", FakeEmailFingerprinter().fingerprint(EMAIL))]
        assert locked.locked(setup.clock.current - timedelta(seconds=1))


class TestEvents:
    def test_the_fifth_failure_emits_lockout_triggered_and_the_next_attempt_names_the_cause(
        self,
    ) -> None:
        setup = Setup(make_account())
        fail(setup, 5)
        with pytest.raises(InvalidCredentialsError):
            setup.use_case.execute(EMAIL, ACCOUNT_SECRET, "203.0.113.7")

        names = [(e.event, e.outcome) for e in setup.events.events]
        assert ("auth.lockout_triggered", Outcome.DENIED) in names
        last = setup.events.events[-1]
        assert last.event == "auth.login_failed"
        assert dict(last.attributes)["cause"] == "account_locked"
        assert last.client_ip == "203.0.113.7"

    def test_login_events_carry_the_step(self) -> None:
        setup = Setup(make_account())
        with pytest.raises(InvalidCredentialsError):
            setup.use_case.execute(EMAIL, WRONG)
        setup.use_case.execute(EMAIL, ACCOUNT_SECRET)

        failed, succeeded = setup.events.events
        assert dict(failed.attributes)["step"] == "password"
        assert dict(succeeded.attributes)["step"] == "password"
        assert EMAIL not in repr(failed.attributes)
