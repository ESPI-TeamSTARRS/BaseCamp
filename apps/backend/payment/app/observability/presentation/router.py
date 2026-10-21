from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.observability.application.exceptions.metrics_not_exposed_error import (
    MetricsNotExposedError,
)
from app.observability.application.observability_services import ObservabilityServices
from app.observability.presentation.dependencies import get_observability_services

router = APIRouter(tags=["observability"])

PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"
# En-têtes qu'ajoute un proxy ou une passerelle : leur présence prouve que la demande est venue de
# l'extérieur du réseau interne (Traefik pose X-Forwarded-*). Défense en profondeur : payment n'est
# de toute façon routé par aucune passerelle.
PROXY_HEADERS = (
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
    "forwarded",
    "x-real-ip",
)

Services = Annotated[ObservabilityServices, Depends(get_observability_services)]


@router.get("/metrics", include_in_schema=False)
def get_metrics(request: Request, services: Services) -> Response:
    """Collecte Prometheus, réseau interne seulement (aucune authentification, aucun routeur)."""
    proxied = any(header in request.headers for header in PROXY_HEADERS)
    try:
        text = services.render_metrics.execute(proxied)
    except MetricsNotExposedError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from None
    return Response(content=text, media_type=PROMETHEUS_CONTENT_TYPE)
