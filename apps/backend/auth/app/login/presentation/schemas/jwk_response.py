from pydantic import BaseModel


class JwkResponse(BaseModel):
    """Cle publique Ed25519 au format JWK (RFC 8037) : jamais de parametre prive."""

    kty: str = "OKP"
    crv: str = "Ed25519"
    use: str = "sig"
    alg: str = "EdDSA"
    kid: str
    x: str
