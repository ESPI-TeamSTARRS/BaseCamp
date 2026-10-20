from uuid import UUID

from app.intent.application.dtos.payment_intent_view import PaymentIntentView
from app.intent.domain.exceptions.payment_intent_not_found_error import PaymentIntentNotFoundError
from app.intent.domain.interfaces.payment_intent_repository import PaymentIntentRepository


class GetPaymentIntentUseCase:
    def __init__(self, repository: PaymentIntentRepository) -> None:
        self._repository = repository

    def execute(self, intent_id: str) -> PaymentIntentView:
        try:
            parsed = UUID(intent_id)
        except ValueError:
            raise PaymentIntentNotFoundError from None
        intent = self._repository.get_by_id(parsed)
        if intent is None:
            raise PaymentIntentNotFoundError
        return PaymentIntentView.from_entity(intent)
