from app.account_orders.application import account_order_events as catalog
from app.account_orders.application.link_guest_orders import LinkGuestOrdersUseCase
from app.account_orders.domain.entities.account_order_page import AccountOrderPage
from app.account_orders.domain.interfaces.account_order_reader import AccountOrderReader
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.customer_identity.domain.entities.customer import Customer

MAX_PAGE_SIZE = 50


class ListMyOrdersUseCase:
    """Commandes du client connecte, et seulement les siennes.

    Avant de lister, rattache ses commandes invitees (meme adresse VERIFIEE) : c'est ce qui fait
    « retrouver ses commandes a la connexion » sans que le front ait a le demander. Un echec du
    rattachement (auth arrete) n'empeche jamais la liste.
    """

    def __init__(
        self,
        reader: AccountOrderReader,
        linker: LinkGuestOrdersUseCase,
        events: BusinessEventLogger,
    ) -> None:
        self._reader = reader
        self._linker = linker
        self._events = events

    def execute(self, customer: Customer, limit: int, offset: int) -> AccountOrderPage:
        limit = max(1, min(limit, MAX_PAGE_SIZE))
        offset = max(0, offset)
        self._linker.execute_best_effort(customer)
        page = self._reader.list_for_user(str(customer.id), limit, offset)
        self._events.log(
            BusinessEvent.success(
                catalog.LISTED,
                resource_type=catalog.RESOURCE_ORDER,
                actor_type=catalog.ACTOR_USER,
                actor_id=str(customer.id),
                attributes={"limit": limit, "offset": offset, "returned": len(page.items)},
            )
        )
        return page
