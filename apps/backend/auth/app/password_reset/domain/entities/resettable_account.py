from dataclasses import dataclass
from uuid import UUID

from app.registration.domain.value_objects.email_address import EmailAddress


@dataclass(frozen=True)
class ResettableAccount:
    """Ce que la reinitialisation sait d'un compte : son identifiant et son adresse."""

    id: UUID
    email: EmailAddress
