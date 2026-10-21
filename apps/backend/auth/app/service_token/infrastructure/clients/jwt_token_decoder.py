from typing import Any

import jwt

from app.service_token.domain.entities.token_claims import TokenClaims
from app.service_token.domain.enums.token_use import TokenUse
from app.service_token.domain.exceptions.invalid_token_error import InvalidTokenError
from app.service_token.domain.interfaces.token_decoder import TokenDecoder
from app.service_token.infrastructure.clients.ed25519_key_store import Ed25519KeyStore
from app.service_token.infrastructure.clients.jwt_token_signer import SIGNING_ALGORITHM

REQUIRED_CLAIMS = ["exp", "iat", "iss", "sub", "aud", "jti", "token_use"]


class JwtTokenDecoder(TokenDecoder):
    """Vérifie la signature EdDSA (seul algorithme accepté) et lit les claims.

    L'expiration, l'émetteur, l'audience et la nature sont contrôlés par le cas d'usage avec
    son horloge : ici seules la signature et la forme des claims comptent.
    """

    def __init__(self, key_store: Ed25519KeyStore) -> None:
        self._key_store = key_store

    def decode(self, token: str) -> TokenClaims:
        try:
            payload = jwt.decode(
                token,
                self._key_store.public_key_pem,
                algorithms=[SIGNING_ALGORITHM],
                options={
                    "require": REQUIRED_CLAIMS,
                    "verify_exp": False,
                    "verify_iat": False,
                    "verify_nbf": False,
                    "verify_aud": False,
                    "verify_iss": False,
                },
            )
            return _to_claims(payload)
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as error:
            raise InvalidTokenError from error


def _to_claims(payload: dict[str, Any]) -> TokenClaims:
    audience = payload["aud"]
    if not isinstance(audience, str):
        raise InvalidTokenError
    return TokenClaims(
        subject=str(payload["sub"]),
        audience=audience,
        scopes=frozenset(str(payload.get("scope", "")).split()),
        issuer=str(payload["iss"]),
        issued_at=int(payload["iat"]),
        expires_at=int(payload["exp"]),
        token_id=str(payload["jti"]),
        token_use=TokenUse(payload["token_use"]),
    )
