from pydantic import BaseModel

from app.service_token.presentation.schemas.jwk_response import JwkResponse


class JwksResponse(BaseModel):
    keys: list[JwkResponse]
