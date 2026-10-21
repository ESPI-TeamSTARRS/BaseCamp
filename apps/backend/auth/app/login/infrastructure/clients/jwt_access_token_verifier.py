from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import jwt

from app.login.domain.entities.access_token_claims import AccessTokenClaims
from app.login.domain.enums.token_rejection import TokenRejection
from app.login.domain.exceptions.access_token_rejected_error import AccessTokenRejectedError
from app.login.domain.interfaces.access_token_verifier import AccessTokenVerifier
from app.login.infrastructure.clients.ed25519_key_ring import Ed25519KeyRing
from app.login.infrastructure.clients.jwt_access_token_signer import ALGORITHM, TOKEN_USE_CLIENT

MAX_TOKEN_LENGTH = 4096
REQUIRED_CLAIMS = ["iss", "aud", "sub", "roles", "token_use", "iat", "exp", "jti"]


class JwtAccessTokenVerifier(AccessTokenVerifier):
    """Verification stricte : EdDSA seul, cle choisie par `kid` dans le trousseau, emetteur,
    audience et usage controles, expiration jugee sur l'horloge fournie.
    """

    def __init__(self, keys: Ed25519KeyRing, issuer: str, audience: str) -> None:
        self._keys = keys
        self._issuer = issuer
        self._audience = audience

    def verify(self, token: str, now: datetime) -> AccessTokenClaims:
        payload = self._decode(token)
        try:
            claims = self._claims(payload)
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            raise self._rejected(TokenRejection.INVALID) from None
        if claims.expires_at <= now:
            raise self._rejected(TokenRejection.EXPIRED)
        return claims

    def _decode(self, token: str) -> dict[str, Any]:
        if not token or len(token) > MAX_TOKEN_LENGTH:
            raise self._rejected(TokenRejection.INVALID)
        try:
            kid = jwt.get_unverified_header(token).get("kid")
            key = self._keys.verification_key(kid) if isinstance(kid, str) else None
            if key is None:
                raise self._rejected(TokenRejection.INVALID)
            payload: dict[str, Any] = jwt.decode(
                token,
                key,
                algorithms=[ALGORITHM],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": REQUIRED_CLAIMS, "verify_exp": False},
            )
        except (jwt.PyJWTError, ValueError, UnicodeError):
            raise self._rejected(TokenRejection.INVALID) from None
        if payload.get("token_use") != TOKEN_USE_CLIENT:
            raise self._rejected(TokenRejection.INVALID)
        return payload

    @staticmethod
    def _claims(payload: dict[str, Any]) -> AccessTokenClaims:
        roles = payload["roles"]
        if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
            raise TypeError("roles")
        verified = payload.get("email_verified", False)
        if not isinstance(verified, bool) or not isinstance(payload["jti"], str):
            raise TypeError("claims")
        return AccessTokenClaims(
            UUID(payload["sub"]),
            tuple(roles),
            verified,
            datetime.fromtimestamp(int(payload["iat"]), UTC),
            datetime.fromtimestamp(int(payload["exp"]), UTC),
            payload["jti"],
        )

    @staticmethod
    def _rejected(rejection: TokenRejection) -> AccessTokenRejectedError:
        return AccessTokenRejectedError(rejection)
