from dataclasses import dataclass

from app.registration.domain.value_objects.email_address import EmailAddress


@dataclass(frozen=True)
class PendingChangeNotice:
    """Notification de changement a envoyer apres la reponse HTTP."""

    to: EmailAddress
