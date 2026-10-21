from dataclasses import dataclass


@dataclass(frozen=True)
class AccountProfile:
    """Ce qu'`auth` affirme du compte a l'instant de l'appel : adresse et verification de l'adresse."""

    email: str
    email_verified: bool
