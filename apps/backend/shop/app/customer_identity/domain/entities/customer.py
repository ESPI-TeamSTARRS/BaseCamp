from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Customer:
    """Client connecte tel que l'affirme son jeton signe : identifiant du compte et etat de l'email.

    Rien d'autre n'est copie du compte (ni adresse, ni nom) : `shop` ne conserve que l'identifiant.
    """

    id: UUID
    email_verified: bool
    token: str
