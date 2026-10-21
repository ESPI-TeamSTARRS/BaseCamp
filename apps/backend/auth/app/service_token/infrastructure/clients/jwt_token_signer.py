import jwt

from app.service_token.domain.entities.token_claims import TokenClaims
from app.service_token.domain.interfaces.token_signer import TokenSigner
from app.service_token.infrastructure.clients.ed25519_key_store import Ed25519KeyStore

SIGNING_ALGORITHM = "EdDSA"


class JwtTokenSigner(TokenSigner):
    def __init__(self, key_store: Ed25519KeyStore) -> None:
        self._key_store = key_store

    def sign(self, claims: TokenClaims) -> str:
        payload = {
            "iss": claims.issuer,
            "sub": claims.subject,
            "aud": claims.audience,
            "scope": " ".join(sorted(claims.scopes)),
            "iat": claims.issued_at,
            "exp": claims.expires_at,
            "jti": claims.token_id,
            "token_use": claims.token_use.value,
        }
        return jwt.encode(
            payload,
            self._key_store.private_key_pem,
            algorithm=SIGNING_ALGORITHM,
            headers={"kid": self._key_store.key_id},
        )
