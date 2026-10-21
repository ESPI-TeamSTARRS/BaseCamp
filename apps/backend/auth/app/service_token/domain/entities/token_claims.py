from dataclasses import dataclass

from app.service_token.domain.enums.token_use import TokenUse


@dataclass(frozen=True)
class TokenClaims:
    """Revendications d'un jeton signé (secondes Unix pour `issued_at` et `expires_at`)."""

    subject: str
    audience: str
    scopes: frozenset[str]
    issuer: str
    issued_at: int
    expires_at: int
    token_id: str
    token_use: TokenUse
