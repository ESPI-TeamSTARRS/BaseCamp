from pydantic import BaseModel


class ShippingAddressResponse(BaseModel):
    full_name: str
    line1: str
    line2: str | None
    postal_code: str
    city: str
    country: str
