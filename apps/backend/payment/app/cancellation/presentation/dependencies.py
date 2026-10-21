from typing import cast

from fastapi import Request

from app.cancellation.application.cancellation_services import CancellationServices


def get_cancellation_services(request: Request) -> CancellationServices:
    """Les cas d'usage sont câblés dans main.py (la présentation n'importe pas l'infrastructure)."""
    return cast(CancellationServices, request.app.state.cancellation_services)
