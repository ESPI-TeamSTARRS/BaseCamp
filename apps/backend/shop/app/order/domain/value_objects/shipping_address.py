from dataclasses import dataclass

from app.order.domain.enums.shipping_country import ShippingCountry


@dataclass(frozen=True)
class ShippingAddress:
    full_name: str
    line1: str
    line2: str | None
    postal_code: str
    city: str
    country: ShippingCountry
