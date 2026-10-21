from collections.abc import Callable
from datetime import datetime, timedelta

from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.order_expiration.application.expiration_report import ExpirationReport
from app.order_expiration.domain.entities.expirable_order import ExpirableOrder
from app.order_expiration.domain.interfaces.expiration_unit_of_work import ExpirationUnitOfWork

ORDER_EXPIRED = "order.expired"
EXPIRATION_COMPLETED = "order.expiration_completed"
DEFAULT_BATCH_SIZE = 100


class ExpireUnpaidOrdersUseCase:
    """Expire les commandes impayées après le délai et rend leur stock, sans état en mémoire.

    L'horloge est injectée. Chaque lot est une transaction : une commande payée n'est jamais
    sélectionnée (statut relu sous verrou) et un rejeu ne rend jamais le stock deux fois.
    """

    def __init__(
        self,
        uow_factory: Callable[[], ExpirationUnitOfWork],
        events: BusinessEventLogger,
        clock: Callable[[], datetime],
        ttl_minutes: int,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        if ttl_minutes <= 0 or batch_size <= 0:
            raise ValueError("the expiration delay and the batch size must be positive")
        self._uow_factory = uow_factory
        self._events = events
        self._clock = clock
        self._ttl = timedelta(minutes=ttl_minutes)
        self._batch_size = batch_size

    def execute(self) -> ExpirationReport:
        now = self._clock()
        cutoff = now - self._ttl
        expired_orders = 0
        released_units = 0
        while True:
            batch = self._expire_batch(cutoff, now)
            expired_orders += len(batch)
            released_units += sum(units for _, units, _ in batch)
            if len(batch) < self._batch_size:
                break
        if expired_orders:
            self._events.log(
                BusinessEvent.success(
                    EXPIRATION_COMPLETED,
                    attributes={"expired_orders": expired_orders, "released_units": released_units},
                )
            )
        return ExpirationReport(expired_orders, released_units)

    def _expire_batch(
        self, cutoff: datetime, now: datetime
    ) -> list[tuple[ExpirableOrder, int, int]]:
        with self._uow_factory() as uow:
            orders = uow.orders.find_expirable(cutoff, self._batch_size)
            done: list[tuple[ExpirableOrder, int, int]] = []
            for order in orders:
                uow.orders.expire(order.id)
                lines = uow.orders.release_reservations(order.id)
                done.append((order, sum(line.quantity for line in lines), len(lines)))
            uow.commit()
        for order, units, line_count in done:
            self._events.log(
                BusinessEvent.success(
                    ORDER_EXPIRED,
                    resource_type="order",
                    resource_id=order.number,
                    attributes={
                        "released_units": units,
                        "line_count": line_count,
                        "age_minutes": int((now - order.created_at).total_seconds() // 60),
                    },
                )
            )
        return done
