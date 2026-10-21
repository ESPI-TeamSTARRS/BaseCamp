from pydantic import BaseModel, ConfigDict, Field


class OrderLineRequest(BaseModel):
    """Seuls productId et quantity sont acceptes : aucun prix ne vient du client."""

    model_config = ConfigDict(extra="forbid", populate_by_name=False)

    product_id: str = Field(alias="productId", min_length=1, max_length=64)
    quantity: int = Field(ge=1, le=10, strict=True)
