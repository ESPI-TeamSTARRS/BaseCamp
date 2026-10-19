from fastapi import APIRouter

from app.core.config import Settings
from app.health.application.get_health import GetHealthUseCase
from app.health.presentation.schemas.health_response import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    result = GetHealthUseCase(service_name=Settings().service_name).execute()
    return HealthResponse(service=result.service, status=result.status.value)
