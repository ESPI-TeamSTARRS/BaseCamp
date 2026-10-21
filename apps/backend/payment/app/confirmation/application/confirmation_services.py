from dataclasses import dataclass

from app.confirmation.application.confirm_payment import ConfirmPaymentUseCase


@dataclass(frozen=True)
class ConfirmationServices:
    """Cas d'usage de la tranche, câblés dans wiring.py et lus par la présentation."""

    confirm: ConfirmPaymentUseCase
