from typing import cast

from fastapi import Request

from app.health.application.get_readiness import GetReadinessUseCase


def get_readiness_use_case(request: Request) -> GetReadinessUseCase:
    """Le cas d'usage est cable dans main.py (la presentation n'importe pas l'infrastructure)."""
    return cast(GetReadinessUseCase, request.app.state.readiness_use_case)
