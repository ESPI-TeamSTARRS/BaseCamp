from dataclasses import dataclass

from app.payment_confirmation.domain.entities.confirmation_mail import ConfirmationMail
from app.payment_confirmation.domain.enums.webhook_outcome import WebhookOutcome


@dataclass(frozen=True)
class WebhookReceipt:
    """Ce que la route doit savoir : le résultat à annoncer et l'email à envoyer après le commit."""

    outcome: WebhookOutcome
    reason: str | None
    mail: ConfirmationMail | None

    @property
    def is_rejected(self) -> bool:
        return self.outcome is WebhookOutcome.REJECTED
