from dataclasses import dataclass

from app.caller_identity.application.authenticate_caller import AuthenticateCallerUseCase
from app.intent.application.create_payment_intent import CreatePaymentIntentUseCase
from app.intent.application.get_payment_intent import GetPaymentIntentUseCase
from app.intent.application.get_payment_intent_by_order import GetPaymentIntentByOrderUseCase


@dataclass(frozen=True)
class IntentServices:
    """Cas d'usage de la tranche, câblés dans wiring.py et lus par la présentation."""

    authenticate: AuthenticateCallerUseCase
    create: CreatePaymentIntentUseCase
    get_by_id: GetPaymentIntentUseCase
    get_by_order: GetPaymentIntentByOrderUseCase
