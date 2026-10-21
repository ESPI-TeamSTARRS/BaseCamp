from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.intent.application.dtos.payment_intent_view import PaymentIntentView
from app.intent.domain.exceptions.payment_intent_not_found_error import PaymentIntentNotFoundError
from app.intent.domain.interfaces.payment_intent_repository import PaymentIntentRepository


class GetPaymentIntentByOrderUseCase:
    def __init__(self, repository: PaymentIntentRepository, events: BusinessEventLogger) -> None:
        self._repository = repository
        self._events = events

    def execute(self, order_reference: str) -> PaymentIntentView:
        intent = self._repository.get_by_order_reference(order_reference)
        if intent is None:
            self._events.log(
                BusinessEvent.denied(
                    "payment.intent_read",
                    "not_found",
                    resource_type="payment_intent",
                    attributes={"lookup": "order"},
                )
            )
            raise PaymentIntentNotFoundError
        self._events.log(
            BusinessEvent.success(
                "payment.intent_read",
                resource_type="payment_intent",
                resource_id=str(intent.id),
                attributes={"lookup": "order"},
            )
        )
        return PaymentIntentView.from_entity(intent)
