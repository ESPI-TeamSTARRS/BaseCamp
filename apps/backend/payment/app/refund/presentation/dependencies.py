from typing import cast

from fastapi import Request

from app.refund.application.refund_services import RefundServices


def get_refund_services(request: Request) -> RefundServices:
    """Les cas d'usage sont câblés dans main.py (la présentation n'importe pas l'infrastructure)."""
    return cast(RefundServices, request.app.state.refund_services)
