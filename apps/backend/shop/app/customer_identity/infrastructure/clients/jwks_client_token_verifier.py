import base64
import binascii
import json
from datetime import datetime
from typing import Any
from uuid import UUID

import jwt
from jwt import PyJWK

from app.customer_identity.domain.entities.customer import Customer
from app.customer_identity.domain.exceptions.client_token_rejected_error import (
    ClientTokenRejectedError,
    TokenRejection,
)
from app.customer_identity.domain.interfaces.client_token_verifier import ClientTokenVerifier
from app.customer_identity.infrastructure.clients.jwks_key_cache import JwksKeyCache

ALGORITHM = "EdDSA"  # jamais `none`, jamais HS* : seul l'algorithme d'`auth` est accepte
CLIENT_TOKEN_USE = "client"  # noqa: S105
CLOCK_TOLERANCE_SECONDS = 30
JWT_SEGMENTS = 3
REQUIRED_CLAIMS = ["exp", "iat", "iss", "aud", "sub", "jti"]


class JwksClientTokenVerifier(ClientTokenVerifier):
    """Verifie localement un jeton client d'`auth` : signature EdDSA par `kid`, `iss`, `aud`, `exp`.

    Contrat de verification d'`auth` : en-tete `kid` obligatoire, `token_use` = `client`, claims
    `sub`, `roles`, `jti` presents; aucune requete vers `auth` pour un jeton dont la cle est connue.
    """

    def __init__(self, keys: JwksKeyCache, issuer: str, audience: str) -> None:
        self._keys = keys
        self._issuer = issuer
        self._audience = audience

    def verify(self, token: str, now: datetime) -> Customer:
        header = self._header(token)
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise ClientTokenRejectedError(TokenRejection.MISSING_KEY_ID)
        if header.get("alg") != ALGORITHM:
            raise ClientTokenRejectedError(TokenRejection.BAD_ALGORITHM)
        jwk = self._keys.key_for(kid)  # peut lever VerificationKeysUnavailableError
        if jwk is None:
            raise ClientTokenRejectedError(TokenRejection.UNKNOWN_KEY)
        claims = self._decode(token, jwk)
        self._check_expiry(claims, now)
        return self._customer(claims, token)

    @staticmethod
    def _header(token: str) -> dict[str, Any]:
        """En-tete JOSE seul, pour choisir la cle (`kid`) : aucune revendication n'est lue ici.

        Le jeton n'est accepte qu'apres `jwt.decode` (signature, emetteur, audience), qui impose
        l'algorithme et la cle choisis, jamais ceux de l'en-tete.
        """
        segments = token.split(".")
        if len(segments) != JWT_SEGMENTS:
            raise ClientTokenRejectedError(TokenRejection.INVALID)
        try:
            padded = segments[0] + "=" * (-len(segments[0]) % 4)
            header = json.loads(base64.urlsafe_b64decode(padded))
        except (ValueError, binascii.Error):
            raise ClientTokenRejectedError(TokenRejection.INVALID) from None
        if not isinstance(header, dict):
            raise ClientTokenRejectedError(TokenRejection.INVALID)
        return header

    def _decode(self, token: str, jwk: Any) -> dict[str, Any]:
        try:
            key = PyJWK(dict(jwk)).key
            return dict(
                jwt.decode(
                    token,
                    key,
                    algorithms=[ALGORITHM],
                    issuer=self._issuer,
                    audience=self._audience,
                    leeway=CLOCK_TOLERANCE_SECONDS,
                    options={"require": REQUIRED_CLAIMS, "verify_exp": False, "verify_iat": False},
                )
            )
        except jwt.InvalidIssuerError:
            raise ClientTokenRejectedError(TokenRejection.WRONG_ISSUER) from None
        except jwt.InvalidAudienceError:
            raise ClientTokenRejectedError(TokenRejection.WRONG_AUDIENCE) from None
        except (jwt.PyJWTError, ValueError, TypeError):
            raise ClientTokenRejectedError(TokenRejection.INVALID) from None

    @staticmethod
    def _check_expiry(claims: dict[str, Any], now: datetime) -> None:
        """L'expiration est jugee avec l'horloge du service (la meme que les autres decisions)."""
        expires = claims.get("exp")
        if isinstance(expires, bool) or not isinstance(expires, int | float):
            raise ClientTokenRejectedError(TokenRejection.INVALID)
        if now.timestamp() > expires + CLOCK_TOLERANCE_SECONDS:
            raise ClientTokenRejectedError(TokenRejection.EXPIRED)

    @staticmethod
    def _customer(claims: dict[str, Any], token: str) -> Customer:
        if claims.get("token_use") != CLIENT_TOKEN_USE:
            raise ClientTokenRejectedError(TokenRejection.NOT_A_CLIENT_TOKEN)
        try:
            return Customer(UUID(str(claims["sub"])), claims.get("email_verified") is True, token)
        except ValueError:
            raise ClientTokenRejectedError(TokenRejection.INVALID) from None
