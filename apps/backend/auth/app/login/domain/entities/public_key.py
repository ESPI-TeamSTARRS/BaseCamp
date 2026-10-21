from dataclasses import dataclass


@dataclass(frozen=True)
class PublicKey:
    """Cle publique de verification du JWKS : identifiant et point Ed25519 (base64url)."""

    kid: str
    x: str
