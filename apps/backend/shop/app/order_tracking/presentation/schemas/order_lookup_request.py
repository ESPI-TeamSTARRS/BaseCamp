from pydantic import BaseModel, ConfigDict, Field


class OrderLookupRequest(BaseModel):
    """Numéro et email : les deux sont requis, rien d'autre n'est accepté."""

    model_config = ConfigDict(extra="forbid", populate_by_name=False)

    order_number: str = Field(alias="orderNumber", pattern=r"^BC-[A-Z0-9]{10}$")
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)
