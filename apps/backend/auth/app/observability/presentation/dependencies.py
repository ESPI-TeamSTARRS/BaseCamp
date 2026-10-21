from typing import cast

from fastapi import Request

from app.observability.application.observability_services import ObservabilityServices


def get_observability_services(request: Request) -> ObservabilityServices:
    """Les cas d'usage sont câblés dans main.py (la présentation n'importe pas l'infrastructure)."""
    return cast(ObservabilityServices, request.app.state.observability_services)
