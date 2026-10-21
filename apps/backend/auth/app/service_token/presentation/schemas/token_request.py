from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TokenRequest(BaseModel):
    """Demande de jeton (flux client_credentials). Tout champ en trop est refuse."""

    model_config = ConfigDict(extra="forbid")

    grant_type: Literal["client_credentials"]
    client_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    client_secret: str = Field(min_length=1, max_length=256, repr=False)
    audience: str = Field(max_length=64)
    scope: str = Field(max_length=255)
