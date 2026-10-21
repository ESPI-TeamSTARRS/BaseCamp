from pydantic import BaseModel, ConfigDict, Field

from app.cart.presentation.schemas.cart_line_request import CartLineRequest


class PayRequest(BaseModel):
    """Commande à payer : aucun montant, il est calculé par le serveur à partir du panier."""

    model_config = ConfigDict(extra="forbid")

    order_reference: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    lines: list[CartLineRequest] = Field(min_length=1, max_length=50)
