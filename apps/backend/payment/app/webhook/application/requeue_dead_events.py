from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.webhook.application import webhook_event_names as names
from app.webhook.domain.interfaces.delivery_unit_of_work import DeliveryUnitOfWork


class RequeueDeadEventsUseCase:
    """Commande d'exploitation : relance un événement `dead` (ou tous) avec un nouveau budget.

    L'identifiant et le corps ne changent pas : la boutique reçoit le même événement et le
    déduplique, la relance n'a donc pas de second effet côté boutique.
    """

    def __init__(
        self,
        unit_of_work: DeliveryUnitOfWork,
        clock: Callable[[], datetime],
        events: BusinessEventLogger,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._events = events

    def execute(self, event_id: UUID | None) -> int:
        with self._unit_of_work.begin() as session:
            requeued = [event.requeue(self._clock()) for event in session.find_dead(event_id)]
            for event in requeued:
                session.save(event)
        for event in requeued:
            self._events.log(
                BusinessEvent.success(
                    names.WEBHOOK_EVENT_REQUEUED,
                    resource_type="webhook_event",
                    resource_id=str(event.id),
                    actor_type="service",
                    actor_id="operations",
                    attributes={
                        "event_type": event.event_type.value,
                        "payment_intent_id": str(event.intent_id),
                    },
                )
            )
        return len(requeued)
