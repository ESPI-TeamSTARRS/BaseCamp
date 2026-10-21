from typing import cast

from fastapi import Request

from app.service_token.application.service_token_services import ServiceTokenServices


def get_service_token_services(request: Request) -> ServiceTokenServices:
    """Les cas d'usage sont cables dans main.py (la presentation n'importe pas l'infrastructure)."""
    return cast(ServiceTokenServices, request.app.state.service_token_services)
