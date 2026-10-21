from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class ManagedAccount:
    """Compte vu par l'administration : jamais le hachage du mot de passe."""

    id: UUID
    email: str
    role: str
    email_verified: bool
    disabled: bool
    created_at: datetime

    @property
    def active_operator(self) -> bool:
        return self.role == "operator" and not self.disabled
