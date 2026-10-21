from pydantic import BaseModel

from app.login.presentation.schemas.jwk_response import JwkResponse


class JwksResponse(BaseModel):
    keys: list[JwkResponse]
