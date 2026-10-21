from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.login.application.get_public_keys import GetPublicKeysUseCase
from app.login.presentation.dependencies import get_public_keys_use_case
from app.login.presentation.schemas.jwk_response import JwkResponse
from app.login.presentation.schemas.jwks_response import JwksResponse

router = APIRouter(tags=["login"])

JWKS_CACHE = "public, max-age=300"  # les services de verification peuvent garder les cles 5 minutes


@router.get("/.well-known/jwks.json", response_model=JwksResponse)
def jwks(
    response: Response,
    use_case: Annotated[GetPublicKeysUseCase, Depends(get_public_keys_use_case)],
) -> JwksResponse:
    response.headers["Cache-Control"] = JWKS_CACHE
    return JwksResponse(keys=[JwkResponse(kid=key.kid, x=key.x) for key in use_case.execute()])
