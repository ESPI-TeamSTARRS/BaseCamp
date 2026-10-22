from app.payment_confirmation.domain.entities.confirmation_mail import ConfirmationMail


def _euros(cents: int) -> str:
    whole, fraction = divmod(cents, 100)
    return f"{whole},{fraction:02d} EUR"


class ConfirmationMailText:
    """Sujet et corps texte de l'email de confirmation (le HTML en est dérivé, une seule source)."""

    @staticmethod
    def subject(mail: ConfirmationMail) -> str:
        return f"Commande {mail.order_number} confirmée"

    @staticmethod
    def body(mail: ConfirmationMail) -> str:
        lines = [
            f"- {line.quantity} x {line.name} : {_euros(line.line_total_cents)}"
            for line in mail.lines
        ]
        return "\n".join(
            [
                "Bonjour,",
                "",
                f"Votre paiement est confirmé. Numéro de commande : {mail.order_number}",
                *lines,
                "",
                f"Total : {_euros(mail.total_cents)}",
                "",
                "L'équipe Basecamp",
            ]
        )
