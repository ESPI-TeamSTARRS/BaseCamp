from dataclasses import dataclass

from app.payment_confirmation.domain.entities.confirmation_mail import ConfirmationMail
from app.payment_confirmation.domain.enums.webhook_outcome import WebhookOutcome


@dataclass(frozen=True)
class AppliedEvent:
    """Résultat de l'application d'un événement dans la transaction en cours."""

    outcome: WebhookOutcome
    reason: str | None = None
    order_id: str | None = None
    order_number: str | None = None
    confirmed: bool = False  # vrai : cet événement confirme le paiement de la commande
    mail: ConfirmationMail | None = None
    refunded_cents: int | None = None  # cumul remboursé enregistré par cet événement
