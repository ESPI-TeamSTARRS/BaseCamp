"""Cles Ed25519 et jetons tels que les emet `auth` (memes en-tetes, memes claims), pour les tests."""

import base64
import time
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

from app.caller_identity.domain.interfaces.jwks_source import JwksSource

ISSUER = "basecamp-auth"
SERVICE_AUDIENCE = "payment"
CLIENT_AUDIENCE = "basecamp-client-api"
TEN_YEARS = 10 * 365 * 24 * 3600


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
        *,
        sub: str = "shop",
        use: str = "service",
        audience: str | None = None,
        scope: str | None = "payments:write",
        roles: list[str] | None = None,
        issuer: str = ISSUER,
        issued_at: float | None = None,
        lifetime: int = TEN_YEARS,
        algorithm: str = "EdDSA",
        headers: dict[str, Any] | None = None,
        drop: tuple[str, ...] = (),
        extra: dict[str, Any] | None = None,
    ) -> str:
        now = issued_at if issued_at is not None else time.time()
        claims: dict[str, Any] = {
            "iss": issuer,
            "sub": sub,
            "aud": audience or (SERVICE_AUDIENCE if use == "service" else CLIENT_AUDIENCE),
            "iat": int(now),
            "exp": int(now) + lifetime,
            "jti": str(uuid4()),
            "token_use": use,
            **(extra or {}),
        }
        if use == "service" and scope is not None:
            claims["scope"] = scope
        if use == "client":
            claims["roles"] = roles if roles is not None else ["customer"]
        for name in drop:
            claims.pop(name, None)
        pem = self._private.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
        return jwt.encode(
            claims, pem, algorithm=algorithm, headers={"kid": self.kid, **(headers or {})}
        )


class StaticJwks(JwksSource):
    def __init__(self, *keys: SigningKey) -> None:
        self.keys = {key.kid: key.jwk for key in keys}
        self.down = False
        self.calls = 0

    def fetch(self) -> Mapping[str, Mapping[str, Any]]:
        from app.caller_identity.domain.exceptions.verification_keys_unavailable_error import (
            VerificationKeysUnavailableError,
        )

        self.calls += 1
        if self.down:
            raise VerificationKeysUnavailableError
        return dict(self.keys)


# Cle unique des tests de la tranche et des routes (injectee par `conftest.py` dans `create_app`).
KEY = SigningKey()
JWKS = StaticJwks(KEY)
SHOP_TOKEN = KEY.token(sub="shop", scope="payments:write")
ADMIN_TOKEN = KEY.token(sub="admin", scope="payments:write")
OPERATOR_TOKEN = KEY.token(sub="operator-1", use="client", roles=["operator"])
# Appelant de service autorise aussi a rembourser (scope `refunds:write`, distinct de `payments:write`).
REFUND_TOKEN = KEY.token(sub="refunder", scope="payments:write refunds:write")
