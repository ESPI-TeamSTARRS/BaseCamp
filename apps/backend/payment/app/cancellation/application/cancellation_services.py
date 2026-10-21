from dataclasses import dataclass

from app.cancellation.application.cancel_payment_intent import CancelPaymentIntentUseCase


@dataclass(frozen=True)
class CancellationServices:
    """Cas d'usage de la tranche, câblés dans wiring.py et lus par la présentation."""

    cancel: CancelPaymentIntentUseCase
