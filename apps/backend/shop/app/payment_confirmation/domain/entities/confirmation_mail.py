from dataclasses import dataclass

from app.payment_confirmation.domain.entities.mail_line import MailLine


@dataclass(frozen=True)
class ConfirmationMail:
    """Ce que l'email de confirmation dit : numéro, lignes et total figés de la commande."""

    to: str
    order_number: str
    total_cents: int
    lines: tuple[MailLine, ...]
