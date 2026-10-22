"""Email de confirmation : envoyé derrière un port, une panne est journalisée mais ne remonte jamais."""

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.payment_confirmation.__tests__.fakes import EMAIL, ORDER_NUMBER, RecordingSender
from app.payment_confirmation.application.send_order_confirmation import (
    SendOrderConfirmationUseCase,
)
from app.payment_confirmation.domain.entities.confirmation_mail import ConfirmationMail
from app.payment_confirmation.domain.entities.mail_line import MailLine
from app.payment_confirmation.domain.errors.confirmation_delivery_error import (
    ConfirmationDeliveryError,
)

MAIL = ConfirmationMail(EMAIL, ORDER_NUMBER, 4490, (MailLine("Popote en titane", 1, 3900),))


class _Pseudonymizer:
    def pseudonymize(self, email: str) -> str:
        return "hash-" + str(len(email))


class TestSendOrderConfirmation:
    def test_sends_the_mail_and_logs_the_success_without_the_address(self) -> None:
        sender, events = RecordingSender(), InMemoryBusinessEventLogger()

        SendOrderConfirmationUseCase(sender, events, _Pseudonymizer()).execute(MAIL)

        assert sender.sent == [MAIL]
        event = events.events[0]
        assert (event.event, event.outcome) == ("order.confirmation_email_sent", Outcome.SUCCESS)
        assert (event.resource_type, event.resource_id) == ("order", ORDER_NUMBER)
        assert EMAIL not in repr(event)

    def test_a_delivery_failure_is_logged_with_the_email_hash_and_never_raised(self) -> None:
        sender, events = RecordingSender(failing=True), InMemoryBusinessEventLogger()

        SendOrderConfirmationUseCase(sender, events, _Pseudonymizer()).execute(MAIL)

        event = events.events[0]
        assert event.event == "order.confirmation_email_failed"
        assert event.outcome is Outcome.ERROR
        assert event.reason == "delivery_failed"
        assert event.attributes["email_hash"] == "hash-" + str(len(EMAIL))
        assert EMAIL not in repr(event)

    def test_the_failure_reason_comes_from_the_adapter_without_any_secret_or_address(self) -> None:
        class _Refusing(RecordingSender):
            def send(self, mail: ConfirmationMail) -> None:
                raise ConfirmationDeliveryError("http_403")

        events = InMemoryBusinessEventLogger()

        SendOrderConfirmationUseCase(_Refusing(), events, _Pseudonymizer()).execute(MAIL)

        failed = events.events[0]
        assert (failed.event, failed.reason) == ("order.confirmation_email_failed", "http_403")
        assert EMAIL not in repr(failed)
