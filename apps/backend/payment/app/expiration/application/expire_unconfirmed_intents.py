from collections.abc import Callable
from datetime import datetime

from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.expiration.application import expiration_event_names as names
from app.expiration.application.dtos.expiration_result import ExpirationResult
from app.expiration.domain.interfaces.intent_expiry_repository import IntentExpiryRepository
from app.intent.domain.entities.payment_intent import PaymentIntent


class ExpireUnconfirmedIntentsUseCase:
    """Expire les intentions non confirmées dont l'échéance est atteinte.

    Sans état en mémoire : c'est la base qui désigne les intentions à expirer (statut et échéance)
    et l'horloge est injectée. Rejoué, le traitement ne trouve plus rien à faire et n'émet rien.
    Aucune écriture au grand livre : une intention expirée n'a jamais été payée.
    """

    def __init__(
        self,
        repository: IntentExpiryRepository,
        clock: Callable[[], datetime],
        batch_size: int,
        events: BusinessEventLogger,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._batch_size = batch_size
        self._events = events

    def execute(self) -> ExpirationResult:
        now = self._clock()
        total = 0
        while True:
            batch = self._repository.expire_overdue(now, self._batch_size)
            for intent in batch:
                self._log_expired(intent)
            total += len(batch)
            if len(batch) < self._batch_size:
                break
        if total:
            self._events.log(
                BusinessEvent.success(
                    names.PAYMENT_EXPIRATION_COMPLETED, attributes={"expired_count": total}
                )
            )
        return ExpirationResult(total)

    def _log_expired(self, intent: PaymentIntent) -> None:
        self._events.log(
            BusinessEvent.success(
                names.PAYMENT_EXPIRED,
                resource_type="payment_intent",
                resource_id=str(intent.id),
                attributes={
                    "order_reference": intent.order_reference,
                    "amount_cents": intent.amount.cents,
                    "currency": intent.currency.value,
                },
            )
        )
