from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.order.domain.interfaces.email_pseudonymizer import EmailPseudonymizer
from app.payment_confirmation.application import payment_webhook_events as names
from app.payment_confirmation.domain.entities.confirmation_mail import ConfirmationMail
from app.payment_confirmation.domain.errors.confirmation_delivery_error import (
    ConfirmationDeliveryError,
)
from app.payment_confirmation.domain.interfaces.confirmation_sender import ConfirmationSender


class SendOrderConfirmationUseCase:
    """Envoie l'email de confirmation après le commit; une panne est journalisée, jamais propagée."""

    def __init__(
        self,
        sender: ConfirmationSender,
        events: BusinessEventLogger,
        pseudonymizer: EmailPseudonymizer,
    ) -> None:
        self._sender = sender
        self._events = events
        self._pseudonymizer = pseudonymizer

    def execute(self, mail: ConfirmationMail) -> None:
        try:
            self._sender.send(mail)
        except ConfirmationDeliveryError:
            self._events.log(
                BusinessEvent.error(
                    names.CONFIRMATION_EMAIL_FAILED,
                    "delivery_failed",
                    resource_type="order",
                    resource_id=mail.order_number,
                    attributes={"email_hash": self._pseudonymizer.pseudonymize(mail.to)},
                )
            )
            return
        self._events.log(
            BusinessEvent.success(
                names.CONFIRMATION_EMAIL_SENT,
                resource_type="order",
                resource_id=mail.order_number,
            )
        )
