from datetime import timedelta

import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.password_reset.__tests__.fakes import FakeResetMailer, FakeResetUnitOfWork, ResetStore
from app.password_reset.application.invalid_new_password_error import InvalidNewPasswordError
from app.password_reset.application.invalid_reset_token_error import InvalidResetTokenError
from app.password_reset.application.request_password_reset import RequestPasswordResetUseCase
from app.password_reset.application.reset_password import ResetPasswordUseCase
from app.registration.__tests__.fakes import (
    FakeClock,
    FakeCommonPasswordList,
    FakeEmailFingerprinter,
    FakePasswordHasher,
    FakeTokenGenerator,
)
from app.registration.domain.services.password_policy import PasswordPolicy

EMAIL = "camille@example.com"
NEW_PASSWORD = "nouveau-sentier-2026"  # noqa: S105


class Harness:
    def __init__(self, mail_fails: bool = False) -> None:
        self.store = ResetStore()
        self.mailer = FakeResetMailer()
        self.tokens = FakeTokenGenerator()
        self.clock = FakeClock()
        self.events = InMemoryBusinessEventLogger()
        self.user_id = self.store.add_account(EMAIL)
        request = RequestPasswordResetUseCase(
            lambda: FakeResetUnitOfWork(self.store),
            self.tokens,
            self.mailer,
            self.clock,
            self.events,
            FakeEmailFingerprinter(),
        )
        pending = request.execute(EMAIL)
        assert pending is not None
        self.token = pending.token
        self.events.events.clear()
        self.mailer.fail = mail_fails
        self.reset = ResetPasswordUseCase(
            lambda: FakeResetUnitOfWork(self.store),
            PasswordPolicy(FakeCommonPasswordList()),
            FakePasswordHasher(),
            self.tokens,
            self.mailer,
            self.clock,
            self.events,
        )


class TestSuccess:
    def test_it_replaces_the_hash_revokes_every_session_and_notifies_the_owner(self) -> None:
        harness = Harness()

        harness.reset.execute(harness.token, NEW_PASSWORD)

        assert harness.store.password_hashes[harness.user_id].startswith("hashed::")
        assert harness.store.revocations == [(harness.user_id, harness.clock.now())]
        assert harness.mailer.changes == [EMAIL]

    def test_it_emits_a_completed_event_without_secret(self) -> None:
        harness = Harness()

        harness.reset.execute(harness.token, NEW_PASSWORD)

        [event] = harness.events.events
        assert (event.event, event.outcome) == ("auth.password_reset_completed", Outcome.SUCCESS)
        assert event.resource_id == str(harness.user_id)
        assert harness.token not in repr(event)
        assert NEW_PASSWORD not in repr(event)

    def test_the_link_is_single_use(self) -> None:
        harness = Harness()
        harness.reset.execute(harness.token, NEW_PASSWORD)

        with pytest.raises(InvalidResetTokenError):
            harness.reset.execute(harness.token, "un-autre-mot-de-passe-42")

    def test_a_notification_failure_is_logged_and_does_not_undo_the_change(self) -> None:
        harness = Harness(mail_fails=True)

        harness.reset.execute(harness.token, NEW_PASSWORD)

        assert harness.store.password_hashes[harness.user_id].startswith("hashed::")
        failure = harness.events.events[-1]
        assert (failure.event, failure.reason) == (
            "auth.email_delivery_failed",
            "mail_delivery_failed",
        )
        assert dict(failure.attributes) == {"kind": "password_changed"}


class TestRefusals:
    def test_unknown_token_gets_the_generic_error_and_changes_nothing(self) -> None:
        harness = Harness()

        with pytest.raises(InvalidResetTokenError) as error:
            harness.reset.execute("jeton-inconnu", NEW_PASSWORD)

        assert error.value.message == "Lien de réinitialisation invalide ou expiré."
        assert harness.store.password_hashes[harness.user_id] == "old-hash"
        assert harness.store.revocations == []
        assert harness.mailer.changes == []
        [event] = harness.events.events
        assert (event.event, event.outcome, event.reason) == (
            "auth.password_reset_rejected",
            Outcome.DENIED,
            "invalid_or_expired_token",
        )

    def test_expired_token_gets_the_same_error(self) -> None:
        harness = Harness()
        harness.clock.current += timedelta(minutes=30)

        with pytest.raises(InvalidResetTokenError):
            harness.reset.execute(harness.token, NEW_PASSWORD)

    def test_a_superseded_token_is_refused(self) -> None:
        harness = Harness()
        request = RequestPasswordResetUseCase(
            lambda: FakeResetUnitOfWork(harness.store),
            harness.tokens,
            harness.mailer,
            harness.clock,
            harness.events,
            FakeEmailFingerprinter(),
        )
        newer = request.execute(EMAIL)
        assert newer is not None

        with pytest.raises(InvalidResetTokenError):
            harness.reset.execute(harness.token, NEW_PASSWORD)
        harness.reset.execute(newer.token, NEW_PASSWORD)

    @pytest.mark.parametrize(
        ("password", "rule"),
        [
            ("court", "password_too_short"),
            ("x" * 129, "password_too_long"),
            ("MotDePasse1234", "password_too_common"),
        ],
    )
    def test_a_weak_password_is_refused_without_consuming_the_token(
        self, password: str, rule: str
    ) -> None:
        harness = Harness()

        with pytest.raises(InvalidNewPasswordError) as error:
            harness.reset.execute(harness.token, password)

        assert error.value.fields == ("password",)
        assert password not in error.value.messages[0]
        [event] = harness.events.events
        assert (event.reason, dict(event.attributes)) == ("weak_password", {"rule": rule})
        assert password not in repr(event)
        harness.reset.execute(harness.token, NEW_PASSWORD)
