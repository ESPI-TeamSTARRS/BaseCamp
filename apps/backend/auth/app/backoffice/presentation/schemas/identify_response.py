from pydantic import BaseModel


class IdentifyResponse(BaseModel):
    """Le defi : identifiant opaque a usage unique et sa duree de vie (secondes)."""

    challenge_id: str
    expires_in: int
