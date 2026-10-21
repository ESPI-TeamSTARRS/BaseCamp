from typing import cast

from fastapi import Request

from app.confirmation.application.confirmation_services import ConfirmationServices


def get_confirmation_services(request: Request) -> ConfirmationServices:
    """Les cas d'usage sont câblés dans main.py (la présentation n'importe pas l'infrastructure)."""
    return cast(ConfirmationServices, request.app.state.confirmation_services)
