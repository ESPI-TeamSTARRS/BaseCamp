import base64
import binascii
import json
from datetime import datetime
from typing import Any

import jwt
from jwt import PyJWK

from app.caller_identity.domain.entities.caller import Caller
from app.caller_identity.domain.enums.token_kind import TokenKind
from app.caller_identity.domain.exceptions.token_rejected_error import (
    TokenRejectedError,
    TokenRejection,
)
from app.caller_identity.domain.interfaces.token_verifier import TokenVerifier
from app.caller_identity.infrastructure.clients.jwks_key_cache import JwksKeyCache

ALGORITHM = "EdDSA"  # jamais `none`, jamais HS* : seul l'algorithme d'`auth` est accepte
CLOCK_TOLERANCE_SECONDS = 30
JWT_SEGMENTS = 3
REQUIRED_CLAIMS = ["exp", "iat", "iss", "aud", "sub", "jti", "token_use"]


class JwksTokenVerifier(TokenVerifier):
    """Verifie localement un jeton d'`auth` : signature EdDSA par `kid`, `iss`, `aud`, `exp`.

    Contrat de verification d'`auth` (docs/services/auth.md) :
    - jeton de SERVICE (`token_use` = `service`) : audience `payment`, claim `scope` (espaces);
    - jeton CLIENT (`token_use` = `client`) : audience des clients, claim `roles`.
    L'audience attendue depend du `token_use` DECLARE, puis la verification impose les deux : un
    jeton client ne passe jamais pour un jeton de service (et inversement), meme signe par la meme cle.
    """

    def __init__(
        self,
        keys: JwksKeyCache,
        issuer: str,
        service_audience: str,
        client_audience: str,
    ) -> None:
        self._keys = keys
        self._issuer = issuer
        self._audience_by_use = {
            TokenKind.SERVICE.value: service_audience,
            TokenKind.CLIENT.value: client_audience,
        }

    def verify(self, token: str, now: datetime) -> Caller:
        header = self._header(token)
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise TokenRejectedError(TokenRejection.MISSING_KEY_ID)
        if header.get("alg") != ALGORITHM:
            raise TokenRejectedError(TokenRejection.BAD_ALGORITHM)
        jwk = self._keys.key_for(kid)  # peut lever VerificationKeysUnavailableError
        if jwk is None:
            raise TokenRejectedError(TokenRejection.UNKNOWN_KEY)
        verified = self._signed_claims(token, jwk)
        self._check_expiry(verified, now)
        return self._caller(verified)

    @staticmethod
    def _header(token: str) -> dict[str, Any]:
        """En-tete JOSE seul, pour choisir la cle (`kid`) : aucune revendication n'est lue ici.

        Le jeton n'est accepte qu'apres `jwt.decode` (signature, emetteur, audience), qui impose
        l'algorithme et la cle choisis, jamais ceux de l'en-tete.
        """
        segments = token.split(".")
        if len(segments) != JWT_SEGMENTS:
            raise TokenRejectedError(TokenRejection.INVALID)
        try:
            padded = segments[0] + "=" * (-len(segments[0]) % 4)
            header = json.loads(base64.urlsafe_b64decode(padded))
        except (ValueError, binascii.Error):
            raise TokenRejectedError(TokenRejection.INVALID) from None
        if not isinstance(header, dict):
            raise TokenRejectedError(TokenRejection.INVALID)
        return header

    def _signed_claims(self, token: str, jwk: Any) -> dict[str, Any]:
        """Signature, emetteur et audience (parmi les deux admises) verifies par `jwt.decode`."""
        try:
            key = PyJWK(dict(jwk)).key
            claims: dict[str, Any] = dict(
                jwt.decode(
                    token,
                    key,
                    algorithms=[ALGORITHM],
                    issuer=self._issuer,
                    audience=list(self._audience_by_use.values()),
                    leeway=CLOCK_TOLERANCE_SECONDS,
                    options={"require": REQUIRED_CLAIMS, "verify_exp": False, "verify_iat": False},
                )
            )
        except jwt.InvalidIssuerError:
            raise TokenRejectedError(TokenRejection.WRONG_ISSUER) from None
        except jwt.InvalidAudienceError:
            raise TokenRejectedError(TokenRejection.WRONG_AUDIENCE) from None
        except (jwt.PyJWTError, ValueError, TypeError):
            raise TokenRejectedError(TokenRejection.INVALID) from None
        return claims

    @staticmethod
    def _check_expiry(claims: dict[str, Any], now: datetime) -> None:
        """L'expiration est jugee avec l'horloge du service (la meme que les autres decisions)."""
        expires = claims.get("exp")
        if isinstance(expires, bool) or not isinstance(expires, int | float):
            raise TokenRejectedError(TokenRejection.INVALID)
        if now.timestamp() > expires + CLOCK_TOLERANCE_SECONDS:
            raise TokenRejectedError(TokenRejection.EXPIRED)

    def _caller(self, claims: dict[str, Any]) -> Caller:
        use = claims.get("token_use")
        expected = self._audience_by_use.get(use) if isinstance(use, str) else None
        if expected is None:
            raise TokenRejectedError(TokenRejection.WRONG_TOKEN_USE)
        audience = claims.get("aud")
        audiences = [audience] if isinstance(audience, str) else list(audience or [])
        if audiences != [expected]:  # `aud` unique et conforme au type de jeton declare
            raise TokenRejectedError(TokenRejection.WRONG_AUDIENCE)
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise TokenRejectedError(TokenRejection.INVALID)
        if use == TokenKind.SERVICE.value:
            scope = claims.get("scope")
            scopes = frozenset(scope.split()) if isinstance(scope, str) else frozenset()
            return Caller(subject, TokenKind.SERVICE, scopes=scopes)
        roles = claims.get("roles")
        names = (
            frozenset(r for r in roles if isinstance(r, str))
            if isinstance(roles, list)
            else frozenset()
        )
        return Caller(subject, TokenKind.CLIENT, roles=names)
