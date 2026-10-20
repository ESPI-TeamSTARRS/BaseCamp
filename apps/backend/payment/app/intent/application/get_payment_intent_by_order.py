from app.intent.application.dtos.payment_intent_view import PaymentIntentView
from app.intent.domain.exceptions.payment_intent_not_found_error import PaymentIntentNotFoundError
from app.intent.domain.interfaces.payment_intent_repository import PaymentIntentRepository


class GetPaymentIntentByOrderUseCase:
    def __init__(self, repository: PaymentIntentRepository) -> None:
        self._repository = repository

    def execute(self, order_reference: str) -> PaymentIntentView:
        intent = self._repository.get_by_order_reference(order_reference)
        if intent is None:
            raise PaymentIntentNotFoundError
        return PaymentIntentView.from_entity(intent)
