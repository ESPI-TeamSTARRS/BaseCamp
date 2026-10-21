from dataclasses import dataclass, field

from app.registration.domain.value_objects.email_address import EmailAddress


@dataclass(frozen=True)
class PendingResetEmail:
    """Email a envoyer apres la reponse HTTP (le temps de reponse ne depend pas de la messagerie)."""

    to: EmailAddress
    token: str = field(repr=False)
