from datetime import timedelta

import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.registration.__tests__.fakes import (
    FakeClock,
    FakeCommonPasswordList,
    FakeEmailFingerprinter,
    FakeMailer,
    FakePasswordHasher,
    FakeStore,
    FakeTokenGenerator,
    FakeUnitOfWork,
)
from app.registration.application.invalid_verification_token_error import (
    InvalidVerificationTokenError,
)
from app.registration.application.register_account import RegisterAccountUseCase
from app.registration.application.verify_email import VerifyEmailUseCase
from app.registration.domain.services.password_policy import PasswordPolicy


class Harness:
    def __init__(self) -> None:
        self.store = FakeStore()
        self.mailer = FakeMailer()
        self.tokens = FakeTokenGenerator()
        self.clock = FakeClock()
        self.events = InMemoryBusinessEventLogger()
        self.register = RegisterAccountUseCase(
            lambda: FakeUnitOfWork(self.store),
            PasswordPolicy(FakeCommonPasswordList()),
            FakePasswordHasher(),
            self.tokens,
            self.mailer,
            self.clock,
            self.events,
            FakeEmailFingerprinter(),
        )
        self.verify = VerifyEmailUseCase(
            lambda: FakeUnitOfWork(self.store), self.tokens, self.clock, self.events
        )

    def registered_token(self) -> str:
        self.register.execute("camille@example.com", "sentier-du-mont-blanc")
        return self.mailer.verifications[-1][1]


class TestVerifyEmail:
    def test_a_valid_token_marks_the_email_as_verified(self) -> None:
        harness = Harness()
        token = harness.registered_token()

        harness.verify.execute(token)

        assert harness.store.users["camille@example.com"].email_verified_at == harness.clock.now()

    def test_a_token_can_only_be_used_once(self) -> None:
        harness = Harness()
        token = harness.registered_token()
        harness.verify.execute(token)

        with pytest.raises(InvalidVerificationTokenError):
            harness.verify.execute(token)

    def test_an_unknown_token_is_rejected(self) -> None:
        harness = Harness()
        harness.registered_token()

        with pytest.raises(InvalidVerificationTokenError):
            harness.verify.execute("jeton-inconnu")

    def test_an_expired_token_is_rejected_and_the_email_stays_unverified(self) -> None:
        harness = Harness()
        token = harness.registered_token()
        harness.clock.current += timedelta(hours=24, seconds=1)

        with pytest.raises(InvalidVerificationTokenError):
            harness.verify.execute(token)

        assert harness.store.users["camille@example.com"].email_verified_at is None

    def test_every_failure_carries_the_same_generic_message(self) -> None:
        harness = Harness()
        token = harness.registered_token()
        harness.verify.execute(token)
        messages = set()

        for candidate in (token, "jeton-inconnu"):
            with pytest.raises(InvalidVerificationTokenError) as raised:
                harness.verify.execute(candidate)
            messages.add(raised.value.message)

        assert len(messages) == 1

    def test_success_emits_email_verified(self) -> None:
        harness = Harness()
        token = harness.registered_token()
        harness.events.events.clear()

        harness.verify.execute(token)

        [event] = harness.events.events
        user = harness.store.users["camille@example.com"]
        assert (event.event, event.outcome, event.reason) == (
            "auth.email_verified",
            Outcome.SUCCESS,
            None,
        )
        assert (event.resource_type, event.resource_id) == ("account", str(user.id))
        assert token not in repr(event)

    def test_failure_emits_a_denied_event_without_the_token(self) -> None:
        harness = Harness()
        harness.events.events.clear()

        with pytest.raises(InvalidVerificationTokenError):
            harness.verify.execute("jeton-inconnu-secret")

        [event] = harness.events.events
        assert (event.event, event.outcome, event.reason) == (
            "auth.email_verification_failed",
            Outcome.DENIED,
            "invalid_or_expired_token",
        )
        assert "jeton-inconnu-secret" not in repr(event)
