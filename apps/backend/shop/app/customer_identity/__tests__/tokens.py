"""Cles Ed25519 et jetons clients tels que les emet `auth` (meme en-tete, memes claims)."""

import base64
import time
from typing import Any
from uuid import UUID, uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

ISSUER = "basecamp-auth"
AUDIENCE = "basecamp-client-api"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class SigningKey:
    """Une paire de cles : signe des jetons et publie sa cle publique au format JWK (RFC 8037)."""

    def __init__(self, kid: str = "kid-1") -> None:
        self.kid = kid
        self._private = Ed25519PrivateKey.generate()

    @property
    def jwk(self) -> dict[str, str]:
        raw = self._private.public_key().public_bytes_raw()
        return {
            "kty": "OKP",
            "crv": "Ed25519",
            "alg": "EdDSA",
            "use": "sig",
            "kid": self.kid,
            "x": _b64(raw),
        }

    def token(
        self,
        subject: UUID | None = None,
        *,
        issued_at: float | None = None,
        lifetime: int = 900,
        email_verified: bool = True,
        use: str = "client",
        issuer: str = ISSUER,
        audience: str = AUDIENCE,
        algorithm: str = "EdDSA",
        headers: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
        drop: tuple[str, ...] = (),
    ) -> str:
        now = issued_at if issued_at is not None else time.time()
        claims: dict[str, Any] = {
            "iss": issuer,
            "aud": audience,
            "sub": str(subject or uuid4()),
            "roles": ["customer"],
            "email_verified": email_verified,
            "token_use": use,
            "iat": int(now),
            "exp": int(now) + lifetime,
            "jti": str(uuid4()),
            **(extra or {}),
        }
        for name in drop:
            claims.pop(name, None)
        header = {"kid": self.kid, **(headers or {})}
        pem = self._private.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
        return jwt.encode(claims, pem, algorithm=algorithm, headers=header)
