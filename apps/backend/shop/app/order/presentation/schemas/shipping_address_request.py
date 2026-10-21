from pydantic import BaseModel, ConfigDict, Field


class ShippingAddressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=False)

    full_name: str = Field(alias="fullName", min_length=1, max_length=120)
    line1: str = Field(min_length=1, max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    postal_code: str = Field(alias="postalCode", min_length=2, max_length=20)
    city: str = Field(min_length=1, max_length=120)
    country: str = Field(min_length=2, max_length=2)  # la liste des pays est une regle metier (422)
