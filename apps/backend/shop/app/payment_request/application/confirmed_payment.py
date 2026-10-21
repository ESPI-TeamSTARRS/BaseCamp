from dataclasses import dataclass

from app.order.domain.enums.order_status import OrderStatus


@dataclass(frozen=True)
class ConfirmedPayment:
    order_number: str
    order_status: OrderStatus
    payment_status: str
