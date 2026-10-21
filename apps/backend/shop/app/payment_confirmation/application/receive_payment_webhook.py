from collections.abc import Callable

from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.payment_confirmation.application import payment_webhook_events as names
from app.payment_confirmation.application.applied_event import AppliedEvent
from app.payment_confirmation.application.apply_payment_event import (
    PAYMENT_FAILED,
    ApplyPaymentEvent,
)
from app.payment_confirmation.application.webhook_receipt import WebhookReceipt
from app.payment_confirmation.domain.entities.payment_event import PaymentEvent
from app.payment_confirmation.domain.enums.webhook_outcome import WebhookOutcome
from app.payment_confirmation.domain.errors.duplicate_webhook_event_error import (
    DuplicateWebhookEventError,
)
from app.payment_confirmation.domain.errors.invalid_webhook_payload_error import (
    InvalidWebhookPayloadError,
)
from app.payment_confirmation.domain.errors.invalid_webhook_signature_error import (
    InvalidWebhookSignatureError,
)
from app.payment_confirmation.domain.interfaces.confirmation_unit_of_work import (
    ConfirmationUnitOfWork,
)
from app.payment_confirmation.domain.services.payment_event_parser import parse_payment_event
from app.payment_confirmation.domain.services.webhook_signature_verifier import (
    WebhookSignatureVerifier,
)
from app.payment_request.application import payment_events

SOURCE = "webhook"


class ReceivePaymentWebhookUseCase:
    """Authentifie un webhook de `payment`, déduplique par id d'événement et l'applique une seule fois."""

    def __init__(
        self,
        uow_factory: Callable[[], ConfirmationUnitOfWork],
        verifier: WebhookSignatureVerifier,
        events: BusinessEventLogger,
        applier: ApplyPaymentEvent | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._verifier = verifier
        self._events = events
        self._applier = applier or ApplyPaymentEvent()

    def execute(
        self, raw_body: bytes, signature_header: str | None, event_id_header: str | None
    ) -> WebhookReceipt:
        event = self._authenticate(raw_body, signature_header, event_id_header)
        try:
            return self._process(event)
        except DuplicateWebhookEventError:
            self._events.log(names.replayed(event))
            return WebhookReceipt(WebhookOutcome.REPLAYED, None, None)

    def _authenticate(
        self, raw_body: bytes, signature_header: str | None, event_id_header: str | None
    ) -> PaymentEvent:
        try:
            self._verifier.verify(signature_header, raw_body)
            event = parse_payment_event(raw_body)
            if event_id_header is not None and event_id_header != event.event_id:
                raise InvalidWebhookPayloadError("event_id_mismatch")
        except (InvalidWebhookSignatureError, InvalidWebhookPayloadError) as error:
            self._events.log(names.rejected(error.reason))
            raise
        return event

    def _process(self, event: PaymentEvent) -> WebhookReceipt:
        with self._uow_factory() as uow:
            if uow.events.exists(event.event_id):
                self._events.log(names.replayed(event))
                return WebhookReceipt(WebhookOutcome.REPLAYED, None, None)
            applied = self._applier.apply(uow, event)
            uow.events.record(
                event.event_id,
                event.event_type,
                applied.outcome,
                applied.reason,
                applied.order_id if applied.confirmed else None,
            )
            uow.commit()
        self._emit(event, applied)
        return WebhookReceipt(applied.outcome, applied.reason, applied.mail)

    def _emit(self, event: PaymentEvent, applied: AppliedEvent) -> None:
        self._events.log(names.received(event))
        if applied.outcome is WebhookOutcome.IGNORED and applied.reason is not None:
            self._events.log(names.ignored(event, applied.reason, applied.order_number))
        elif applied.confirmed and applied.order_number is not None:
            self._events.log(self._paid(event, applied.order_number))
        elif applied.refunded_cents is not None and applied.order_number is not None:
            self._events.log(self._refunded(applied.order_number, applied.refunded_cents))
        elif event.event_type == PAYMENT_FAILED and applied.order_number is not None:
            self._events.log(
                BusinessEvent.denied(
                    names.ORDER_PAYMENT_FAILED,
                    "provider_declined",
                    resource_type="order",
                    resource_id=applied.order_number,
                    attributes={"source": SOURCE},
                )
            )

    def _refunded(self, order_number: str, refunded_cents: int) -> BusinessEvent:
        return BusinessEvent.success(
            names.ORDER_REFUNDED,
            resource_type="order",
            resource_id=order_number,
            attributes={
                "amount_refunded_cents": refunded_cents,
                "currency": names.CURRENCY,
                "source": SOURCE,
            },
        )

    def _paid(self, event: PaymentEvent, order_number: str) -> BusinessEvent:
        return BusinessEvent.success(
            payment_events.ORDER_PAID,
            resource_type="order",
            resource_id=order_number,
            attributes={
                "amount_cents": event.amount_cents,
                "currency": names.CURRENCY,
                "source": SOURCE,
            },
        )
