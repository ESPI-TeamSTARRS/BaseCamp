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
from app.registration.application.invalid_registration_error import InvalidRegistrationError
from app.registration.application.register_account import RegisterAccountUseCase
from app.registration.domain.enums.user_role import UserRole
from app.registration.domain.services.password_policy import PasswordPolicy

STRONG_ENOUGH = "sentier-du-mont-blanc"


class Harness:
    def __init__(self, mail_fails: bool = False) -> None:
        self.store = FakeStore()
        self.hasher = FakePasswordHasher()
        self.mailer = FakeMailer(fail=mail_fails)
        self.tokens = FakeTokenGenerator()
        self.clock = FakeClock()
        self.events = InMemoryBusinessEventLogger()
        self.use_case = RegisterAccountUseCase(
            lambda: FakeUnitOfWork(self.store),
            PasswordPolicy(FakeCommonPasswordList()),
            self.hasher,
            self.tokens,
            self.mailer,
            self.clock,
            self.events,
            FakeEmailFingerprinter(),
        )


class TestRegisterAccount:
    def test_creates_an_unverified_customer_with_a_hashed_password(self) -> None:
        harness = Harness()

        harness.use_case.execute("Camille@Example.com", STRONG_ENOUGH)

        user = harness.store.users["camille@example.com"]
        assert user.role is UserRole.CUSTOMER
        assert user.email_verified_at is None
        assert user.password_hash != STRONG_ENOUGH
        assert STRONG_ENOUGH not in user.password_hash

    def test_sends_a_verification_email_and_stores_only_the_token_hash(self) -> None:
        harness = Harness()

        harness.use_case.execute("camille@example.com", STRONG_ENOUGH)

        [(recipient, raw_token)] = harness.mailer.verifications
        assert recipient == "camille@example.com"
        assert raw_token not in harness.store.tokens
        assert harness.tokens.digest(raw_token) in harness.store.tokens

    def test_token_expires_24_hours_after_registration(self) -> None:
        harness = Harness()

        harness.use_case.execute("camille@example.com", STRONG_ENOUGH)

        [token] = harness.store.tokens.values()
        assert (token.expires_at - harness.clock.now()).total_seconds() == 24 * 3600

    def test_existing_email_creates_nothing_and_warns_the_owner(self) -> None:
        harness = Harness()
        harness.use_case.execute("camille@example.com", STRONG_ENOUGH)
        harness.mailer.verifications.clear()

        harness.use_case.execute(" CAMILLE@example.com", "un-autre-mot-de-passe")

        assert len(harness.store.users) == 1
        assert len(harness.store.tokens) == 1
        assert harness.mailer.verifications == []
        assert harness.mailer.already_exists == ["camille@example.com"]

    def test_existing_email_still_pays_the_hashing_cost(self) -> None:
        harness = Harness()
        harness.use_case.execute("camille@example.com", STRONG_ENOUGH)

        harness.use_case.execute("camille@example.com", STRONG_ENOUGH)

        assert harness.hasher.calls == 2

    def test_invalid_email_is_rejected_before_any_work(self) -> None:
        harness = Harness()

        with pytest.raises(InvalidRegistrationError) as raised:
            harness.use_case.execute("pas-un-email", STRONG_ENOUGH)

        assert raised.value.fields == ("email",)
        assert harness.hasher.calls == 0
        assert harness.store.users == {}

    @pytest.mark.parametrize("password", ["court", "MotDePasse1234"])
    def test_weak_password_is_rejected_with_a_fixed_message(self, password: str) -> None:
        harness = Harness()

        with pytest.raises(InvalidRegistrationError) as raised:
            harness.use_case.execute("camille@example.com", password)

        assert raised.value.fields == ("password",)
        assert password not in raised.value.messages[0]
        assert harness.hasher.calls == 0
        assert harness.mailer.verifications == []

    def test_reports_both_fields_when_both_are_invalid(self) -> None:
        harness = Harness()

        with pytest.raises(InvalidRegistrationError) as raised:
            harness.use_case.execute("nope", "court")

        assert raised.value.fields == ("email", "password")

    @pytest.mark.parametrize("repeat", [False, True])
    def test_a_mail_failure_does_not_change_the_outcome(self, repeat: bool) -> None:
        harness = Harness(mail_fails=True)
        if repeat:
            harness.use_case.execute("camille@example.com", STRONG_ENOUGH)

        harness.use_case.execute("camille@example.com", STRONG_ENOUGH)

        assert "camille@example.com" in harness.store.users

    def test_success_emits_account_registered_with_a_hashed_email(self) -> None:
        harness = Harness()

        harness.use_case.execute("camille@example.com", STRONG_ENOUGH)

        [event] = harness.events.events
        user = harness.store.users["camille@example.com"]
        assert (event.event, event.outcome, event.reason) == (
            "auth.account_registered",
            Outcome.SUCCESS,
            None,
        )
        assert (event.resource_type, event.resource_id) == ("account", str(user.id))
        assert list(event.attributes) == ["email_hash"]
        assert str(event.attributes["email_hash"]).startswith("fp-")
        assert "camille" not in repr(event)

    def test_existing_email_emits_a_denied_registration_rejected(self) -> None:
        harness = Harness()
        harness.use_case.execute("camille@example.com", STRONG_ENOUGH)
        harness.events.events.clear()

        harness.use_case.execute("camille@example.com", STRONG_ENOUGH)

        [event] = harness.events.events
        assert (event.event, event.outcome, event.reason) == (
            "auth.registration_rejected",
            Outcome.DENIED,
            "email_already_used",
        )
        assert "camille" not in repr(event)

    @pytest.mark.parametrize(
        ("email", "password", "reason", "rule"),
        [
            ("pas-un-email", STRONG_ENOUGH, "invalid_email", "email_invalid"),
            ("camille@example.com", "court", "weak_password", "password_too_short"),
            ("camille@example.com", "MotDePasse1234", "weak_password", "password_too_common"),
            ("nope", "court", "invalid_email", "email_invalid"),
        ],
    )
    def test_invalid_input_emits_a_denied_event_without_the_input(
        self, email: str, password: str, reason: str, rule: str
    ) -> None:
        harness = Harness()

        with pytest.raises(InvalidRegistrationError):
            harness.use_case.execute(email, password)

        [event] = harness.events.events
        assert (event.event, event.outcome, event.reason) == (
            "auth.registration_rejected",
            Outcome.DENIED,
            reason,
        )
        assert event.attributes == {"rule": rule}
        rendered = repr(event)
        assert email not in rendered
        assert password not in rendered

    @pytest.mark.parametrize(
        ("repeat", "kind"), [(False, "verification"), (True, "account_exists")]
    )
    def test_a_mail_failure_emits_an_error_event_without_address(
        self, repeat: bool, kind: str
    ) -> None:
        harness = Harness(mail_fails=True)
        if repeat:
            harness.use_case.execute("camille@example.com", STRONG_ENOUGH)
        harness.events.events.clear()

        harness.use_case.execute("camille@example.com", STRONG_ENOUGH)

        failures = [e for e in harness.events.events if e.event == "auth.email_delivery_failed"]
        [failure] = failures
        assert (failure.outcome, failure.reason) == (Outcome.ERROR, "mail_delivery_failed")
        assert failure.attributes == {"kind": kind, "cause": "smtp_error"}

    def test_no_event_contains_the_password_the_token_or_the_address(self) -> None:
        harness = Harness(mail_fails=True)

        harness.use_case.execute("camille@example.com", STRONG_ENOUGH)
        harness.use_case.execute("camille@example.com", STRONG_ENOUGH)

        rendered = repr(harness.events.events)
        password_hash = harness.store.users["camille@example.com"].password_hash
        for secret in (STRONG_ENOUGH, "raw-token", "camille", password_hash):
            assert secret not in rendered
