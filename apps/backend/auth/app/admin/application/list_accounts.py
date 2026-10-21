from uuid import UUID

from app.admin.application import admin_events as catalog
from app.admin.application.account_summary import AccountPageSummary
from app.admin.application.unit_of_work_factory import UnitOfWorkFactory
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger

MAX_PAGE_SIZE = 100


class ListAccountsUseCase:
    """Liste paginee des comptes, journalisee (qui a consulte la liste, quelle page)."""

    def __init__(self, unit_of_work: UnitOfWorkFactory, events: BusinessEventLogger) -> None:
        self._unit_of_work = unit_of_work
        self._events = events

    def execute(
        self, operator_id: UUID, limit: int, offset: int, client_ip: str | None = None
    ) -> AccountPageSummary:
        limit = max(1, min(limit, MAX_PAGE_SIZE))
        offset = max(0, offset)
        with self._unit_of_work() as work:
            page = work.accounts.list_page(limit, offset)
        self._events.log(
            BusinessEvent.success(
                catalog.ACCOUNTS_LISTED,
                resource_type=catalog.RESOURCE_ACCOUNT,
                actor_type=catalog.ACTOR_OPERATOR,
                actor_id=str(operator_id),
                client_ip=client_ip,
                attributes={"limit": limit, "offset": offset, "returned": len(page.items)},
            )
        )
        return AccountPageSummary.of(page)
