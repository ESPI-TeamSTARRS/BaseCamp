from app.account_orders.application import account_order_events as catalog
from app.account_orders.application.account_order_not_found_error import (
    AccountOrderNotFoundError,
)
from app.account_orders.domain.entities.account_order import AccountOrder
from app.account_orders.domain.interfaces.account_order_reader import AccountOrderReader
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.customer_identity.domain.entities.customer import Customer


class GetMyOrderUseCase:
    """Une commande du client connecte. Inconnue ou d'un autre compte : la meme erreur (404)."""

    def __init__(self, reader: AccountOrderReader, events: BusinessEventLogger) -> None:
        self._reader = reader
        self._events = events

    def execute(self, customer: Customer, order_id: str) -> AccountOrder:
        order = self._reader.find_for_user(str(customer.id), order_id)
        if order is None:
            self._events.log(
                BusinessEvent.denied(
                    catalog.VIEW_DENIED,
                    catalog.REASON_NOT_FOUND,
                    resource_type=catalog.RESOURCE_ORDER,
                    actor_type=catalog.ACTOR_USER,
                    actor_id=str(customer.id),
                )
            )
            raise AccountOrderNotFoundError
        return order
