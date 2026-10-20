from uuid import UUID

from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.intent.application.dtos.payment_intent_view import PaymentIntentView
from app.intent.domain.exceptions.payment_intent_not_found_error import PaymentIntentNotFoundError
from app.intent.domain.interfaces.payment_intent_repository import PaymentIntentRepository


class GetPaymentIntentUseCase:
    def __init__(self, repository: PaymentIntentRepository, events: BusinessEventLogger) -> None:
        self._repository = repository
        self._events = events

    def execute(self, intent_id: str) -> PaymentIntentView:
        try:
            view = self._find(intent_id)
        except PaymentIntentNotFoundError:
            self._events.log(
                BusinessEvent.denied(
                    "payment.intent_read",
                    "not_found",
                    resource_type="payment_intent",
                    attributes={"lookup": "id"},
                )
            )
            raise
        self._events.log(
            BusinessEvent.success(
                "payment.intent_read",
                resource_type="payment_intent",
                resource_id=view.id,
                attributes={"lookup": "id"},
            )
        )
        return view

    def _find(self, intent_id: str) -> PaymentIntentView:
        try:
            parsed = UUID(intent_id)
        except ValueError:
            raise PaymentIntentNotFoundError from None
        intent = self._repository.get_by_id(parsed)
        if intent is None:
            raise PaymentIntentNotFoundError
        return PaymentIntentView.from_entity(intent)
