from dataclasses import dataclass

from app.intent.application.authenticate_service import AuthenticateServiceUseCase
from app.intent.application.create_payment_intent import CreatePaymentIntentUseCase
from app.intent.application.get_payment_intent import GetPaymentIntentUseCase
from app.intent.application.get_payment_intent_by_order import GetPaymentIntentByOrderUseCase


@dataclass(frozen=True)
class IntentServices:
    """Cas d'usage de la tranche, câblés dans wiring.py et lus par la présentation."""

    authenticate: AuthenticateServiceUseCase
    create: CreatePaymentIntentUseCase
    get_by_id: GetPaymentIntentUseCase
    get_by_order: GetPaymentIntentByOrderUseCase
