from dataclasses import dataclass

from app.intent.application.dtos.payment_intent_view import PaymentIntentView


@dataclass(frozen=True)
class CreatePaymentIntentResult:
    intent: PaymentIntentView
    created: bool
