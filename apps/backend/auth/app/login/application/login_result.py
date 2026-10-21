from dataclasses import dataclass, field


@dataclass(frozen=True)
class LoginResult:
    """Ce que la connexion remet : jeton d'acces (corps) et jeton de rafraichissement (cookie)."""

    access_token: str = field(repr=False)
    expires_in: int
    refresh_token: str = field(repr=False)
    refresh_expires_in: int
