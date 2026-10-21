from dataclasses import dataclass


@dataclass(frozen=True)
class StockReservation:
    order_id: str
    product_id: str
    quantity: int
