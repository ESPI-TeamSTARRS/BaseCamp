from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, Response, status

from app.health.application.get_health import GetHealthUseCase
from app.health.application.get_readiness import GetReadinessUseCase
from app.health.presentation.dependencies import get_readiness_use_case
from app.health.presentation.schemas.health_response import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def get_health(request: Request) -> HealthResponse:
    """Liveness sur la boucle d'événements : jamais en file derrière les handlers synchrones."""
    result = cast(GetHealthUseCase, request.app.state.health_use_case).execute()
    return HealthResponse(service=result.service, status=result.status.value)


@router.get("/health/ready", response_model=HealthResponse)
def get_ready(
    response: Response,
    use_case: Annotated[GetReadinessUseCase, Depends(get_readiness_use_case)],
) -> HealthResponse:
    result = use_case.execute()
    if not result.is_up:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(service=result.service, status=result.status.value)
