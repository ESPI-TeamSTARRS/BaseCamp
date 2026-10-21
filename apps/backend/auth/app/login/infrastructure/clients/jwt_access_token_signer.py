import jwt

from app.login.domain.entities.access_token_claims import AccessTokenClaims
from app.login.domain.interfaces.access_token_signer import AccessTokenSigner
from app.login.infrastructure.clients.ed25519_key_ring import Ed25519KeyRing

ALGORITHM = "EdDSA"
TOKEN_USE_CLIENT = "client"  # noqa: S105


class JwtAccessTokenSigner(AccessTokenSigner):
    """JWT d'acces client : `aud` dedie et `token_use`=client, pour ne jamais le confondre
    avec un futur jeton de service.
    """

    def __init__(self, keys: Ed25519KeyRing, issuer: str, audience: str) -> None:
        self._keys = keys
        self._issuer = issuer
        self._audience = audience

    def sign(self, claims: AccessTokenClaims) -> str:
        payload = {
            "iss": self._issuer,
            "aud": self._audience,
            "sub": str(claims.subject),
            "roles": list(claims.roles),
            "email_verified": claims.email_verified,
            "token_use": TOKEN_USE_CLIENT,
            "iat": int(claims.issued_at.timestamp()),
            "exp": int(claims.expires_at.timestamp()),
            "jti": claims.token_id,
        }
        return jwt.encode(
            payload,
            self._keys.signing_key,
            algorithm=ALGORITHM,
            headers={"kid": self._keys.signing_kid},
        )
