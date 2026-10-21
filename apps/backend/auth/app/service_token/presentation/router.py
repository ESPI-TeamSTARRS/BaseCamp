from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.service_token.application.commands.issue_service_token_command import (
    IssueServiceTokenCommand,
)
from app.service_token.application.service_token_services import ServiceTokenServices
from app.service_token.presentation.dependencies import get_service_token_services
from app.service_token.presentation.schemas.error_response import ErrorResponse
from app.service_token.presentation.schemas.token_request import TokenRequest
from app.service_token.presentation.schemas.token_response import TokenResponse

# Routes reservees au reseau interne : la passerelle ne les route jamais (404 depuis l'exterieur).
router = APIRouter(prefix="/internal", tags=["internal"])

Services = Annotated[ServiceTokenServices, Depends(get_service_token_services)]


@router.post(
    "/token",
    response_model=TokenResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
)
def issue_token(body: TokenRequest, response: Response, services: Services) -> TokenResponse:
    issued = services.issue.execute(
        IssueServiceTokenCommand(body.client_id, body.client_secret, body.audience, body.scope)
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return TokenResponse(
        access_token=issued.access_token,
        token_type="Bearer",  # noqa: S106 - type de jeton OAuth, pas un secret
        expires_in=issued.expires_in,
        scope=issued.scope,
    )
