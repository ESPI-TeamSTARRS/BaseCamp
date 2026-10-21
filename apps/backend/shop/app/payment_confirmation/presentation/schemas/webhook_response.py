from typing import Literal

from pydantic import BaseModel


class WebhookResponse(BaseModel):
    """Accusé de réception : 200 pour un événement appliqué, ignoré ou déjà vu (jamais de détail)."""

    status: Literal["applied", "ignored", "replayed"]
