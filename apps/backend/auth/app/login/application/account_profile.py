from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class AccountProfile:
    """Profil public du compte connecte (jamais le hachage du mot de passe)."""

    id: UUID
    email: str
    roles: tuple[str, ...]
    email_verified: bool
