from uuid import UUID

from app.admin_orders.application import admin_order_events as catalog
from app.admin_orders.application.admin_order_not_found_error import AdminOrderNotFoundError
from app.admin_orders.domain.entities.admin_order import AdminOrder
from app.admin_orders.domain.interfaces.admin_order_reader import AdminOrderReader
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.order.domain.interfaces.email_pseudonymizer import EmailPseudonymizer


class GetAdminOrderUseCase:
    """Une commande par identifiant, avec son adresse de livraison (jamais journalisee)."""

    def __init__(
        self,
        reader: AdminOrderReader,
        events: BusinessEventLogger,
        pseudonymizer: EmailPseudonymizer,
    ) -> None:
        self._reader = reader
        self._events = events
        self._pseudonymizer = pseudonymizer

    def execute(self, operator_id: UUID, order_id: str) -> AdminOrder:
        actor = self._pseudonymizer.pseudonymize(str(operator_id))
        order = self._reader.find(order_id)
        if order is None:
            self._events.log(
                BusinessEvent.denied(
                    catalog.VIEW_DENIED,
                    catalog.REASON_NOT_FOUND,
                    resource_type=catalog.RESOURCE_ORDER,
                    resource_id=order_id,
                    actor_type=catalog.ACTOR_USER,
                    actor_id=actor,
                )
            )
            raise AdminOrderNotFoundError
        self._events.log(
            BusinessEvent.success(
                catalog.VIEWED,
                resource_type=catalog.RESOURCE_ORDER,
                resource_id=order.id,
                actor_type=catalog.ACTOR_USER,
                actor_id=actor,
            )
        )
        return order
