from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.password_reset.__tests__.fakes import FakeResetMailer, FakeResetUnitOfWork, ResetStore
from app.password_reset.application.request_password_reset import RequestPasswordResetUseCase
from app.registration.__tests__.fakes import FakeClock, FakeEmailFingerprinter, FakeTokenGenerator
from app.registration.domain.value_objects.email_address import EmailAddress

EMAIL = "camille@example.com"


class Harness:
    def __init__(self, mail_fails: bool = False) -> None:
        self.store = ResetStore()
        self.mailer = FakeResetMailer(fail=mail_fails)
        self.tokens = FakeTokenGenerator()
        self.clock = FakeClock()
        self.events = InMemoryBusinessEventLogger()
        self.fingerprinter = FakeEmailFingerprinter()
        self.use_case = RequestPasswordResetUseCase(
            lambda: FakeResetUnitOfWork(self.store),
            self.tokens,
            self.mailer,
            self.clock,
            self.events,
            self.fingerprinter,
        )


class TestKnownAccount:
    def test_it_stores_only_the_hash_of_a_fresh_token_and_returns_the_email_to_send(self) -> None:
        harness = Harness()
        harness.store.add_account(EMAIL)

        pending = harness.use_case.execute(" Camille@Example.com ")

        assert pending is not None
        assert pending.to.value == EMAIL
        assert pending.token not in harness.store.tokens
        assert harness.tokens.digest(pending.token) in harness.store.tokens
        assert pending.token not in repr(pending)

    def test_delivery_sends_the_link_after_the_response(self) -> None:
        harness = Harness()
        harness.store.add_account(EMAIL)
        pending = harness.use_case.execute(EMAIL)
        assert pending is not None

        assert harness.mailer.links == []
        harness.use_case.deliver(pending)

        assert harness.mailer.links == [(EMAIL, pending.token)]

    def test_a_new_request_invalidates_the_previous_link(self) -> None:
        harness = Harness()
        harness.store.add_account(EMAIL)
        first = harness.use_case.execute(EMAIL)
        second = harness.use_case.execute(EMAIL)
        assert first is not None
        assert second is not None

        first_token = harness.store.tokens[harness.tokens.digest(first.token)]
        second_token = harness.store.tokens[harness.tokens.digest(second.token)]
        assert not first_token.is_usable(harness.clock.now())
        assert second_token.is_usable(harness.clock.now())

    def test_it_emits_a_success_event_with_the_fingerprint_only(self) -> None:
        harness = Harness()
        user_id = harness.store.add_account(EMAIL)

        harness.use_case.execute(EMAIL)

        [event] = harness.events.events
        assert event.event == "auth.password_reset_requested"
        assert event.outcome is Outcome.SUCCESS
        assert (event.resource_type, event.resource_id) == ("account", str(user_id))
        expected = harness.fingerprinter.fingerprint(EmailAddress.of(EMAIL))
        assert dict(event.attributes) == {"email_hash": expected}
        assert EMAIL not in repr(event)


class TestUnknownOrRefusedRequests:
    def test_unknown_account_sends_nothing_and_stores_no_token(self) -> None:
        harness = Harness()

        pending = harness.use_case.execute("inconnu@example.com")

        assert pending is None
        assert harness.store.tokens == {}
        [event] = harness.events.events
        assert (event.event, event.outcome, event.reason) == (
            "auth.password_reset_rejected",
            Outcome.DENIED,
            "unknown_account",
        )
        assert "inconnu@example.com" not in repr(event)

    def test_invalid_address_is_a_silent_rejection_logged_without_the_value(self) -> None:
        harness = Harness()

        pending = harness.use_case.execute("pas-un-email")

        assert pending is None
        [event] = harness.events.events
        assert event.reason == "invalid_email"
        assert "pas-un-email" not in repr(event)

    def test_the_per_address_limit_blocks_further_links(self) -> None:
        harness = Harness()
        harness.store.add_account(EMAIL)
        results = [harness.use_case.execute(EMAIL) for _ in range(4)]

        assert [result is not None for result in results] == [True, True, True, False]
        last = harness.events.events[-1]
        assert (last.event, last.reason) == ("auth.password_reset_rejected", "rate_limited")
        assert len(harness.store.tokens) == 3

    def test_the_limit_applies_to_unknown_addresses_too(self) -> None:
        harness = Harness()
        for _ in range(4):
            harness.use_case.execute("inconnu@example.com")

        reasons = [event.reason for event in harness.events.events]
        assert reasons == ["unknown_account"] * 3 + ["rate_limited"]


class TestMailFailure:
    def test_a_mail_outage_is_logged_and_never_raised(self) -> None:
        harness = Harness(mail_fails=True)
        harness.store.add_account(EMAIL)
        pending = harness.use_case.execute(EMAIL)
        assert pending is not None

        harness.use_case.deliver(pending)

        failure = harness.events.events[-1]
        assert (failure.event, failure.outcome, failure.reason) == (
            "auth.email_delivery_failed",
            Outcome.ERROR,
            "mail_delivery_failed",
        )
        assert dict(failure.attributes) == {"kind": "password_reset"}
        assert pending.token not in repr(failure)
