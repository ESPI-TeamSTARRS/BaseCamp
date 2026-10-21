from dataclasses import dataclass


@dataclass(frozen=True)
class PublicJwk:
    """Clé publique Ed25519 de signature (JWK, type OKP) : identifiant et coordonnée base64url."""

    key_id: str
    x: str
