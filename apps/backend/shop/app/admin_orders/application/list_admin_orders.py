from uuid import UUID

from app.admin_orders.application import admin_order_events as catalog
from app.admin_orders.domain.entities.admin_order_page import AdminOrderPage
from app.admin_orders.domain.interfaces.admin_order_reader import AdminOrderReader
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.order.domain.interfaces.email_pseudonymizer import EmailPseudonymizer


class ListAdminOrdersUseCase:
    """Liste paginee des commandes de tous les clients (lecture seule)."""

    def __init__(
        self,
        reader: AdminOrderReader,
        events: BusinessEventLogger,
        pseudonymizer: EmailPseudonymizer,
    ) -> None:
        self._reader = reader
        self._events = events
        self._pseudonymizer = pseudonymizer

    def execute(
        self, operator_id: UUID, status: str | None, search: str | None, limit: int, offset: int
    ) -> AdminOrderPage:
        page = self._reader.list_orders(status, search, limit, offset)
        self._events.log(
            BusinessEvent.success(
                catalog.LISTED,
                resource_type=catalog.RESOURCE_ORDER,
                actor_type=catalog.ACTOR_USER,
                actor_id=self._pseudonymizer.pseudonymize(str(operator_id)),
                # Le texte cherche (un email possible) n'est jamais journalise : seulement qu'il y en avait un.
                attributes={
                    "status": status,
                    "searched": bool(search),
                    "limit": limit,
                    "offset": offset,
                    "returned": len(page.items),
                },
            )
        )
        return page
