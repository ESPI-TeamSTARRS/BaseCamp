from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class Account:
    """Compte vu par la connexion : identifiants, role et etat (actif ou desactive)."""

    id: UUID
    email: str
    password_hash: str = field(repr=False)
    role: str
    email_verified: bool
    disabled: bool
