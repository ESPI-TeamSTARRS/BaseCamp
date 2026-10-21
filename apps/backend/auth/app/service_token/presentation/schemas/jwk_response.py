from pydantic import BaseModel


class JwkResponse(BaseModel):
    kty: str
    crv: str
    alg: str
    use: str
    kid: str
    x: str
