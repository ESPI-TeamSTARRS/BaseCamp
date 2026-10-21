from app.order.application.placed_order import PlacedOrder
from app.order.presentation.schemas.order_line_response import OrderLineResponse
from app.order.presentation.schemas.order_response import OrderResponse
from app.order.presentation.schemas.shipping_address_response import ShippingAddressResponse


class OrderResponseMapper:
    @staticmethod
    def to_response(placed: PlacedOrder) -> OrderResponse:
        order = placed.order
        address = order.address
        return OrderResponse(
            id=order.id,
            number=order.number,
            status=order.status.value,
            email=order.email,
            shipping_address=ShippingAddressResponse(
                full_name=address.full_name,
                line1=address.line1,
                line2=address.line2,
                postal_code=address.postal_code,
                city=address.city,
                country=address.country.value,
            ),
            lines=[
                OrderLineResponse(
                    product_id=line.product_id,
                    name=line.product_name,
                    unit_price_cents=line.unit_price_cents,
                    quantity=line.quantity,
                    line_total_cents=line.line_total_cents,
                )
                for line in order.lines
            ],
            subtotal_cents=order.subtotal_cents,
            shipping_cents=order.shipping_cents,
            total_cents=order.total_cents,
            created_at=order.created_at,
        )
