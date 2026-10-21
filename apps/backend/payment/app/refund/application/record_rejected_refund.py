from uuid import UUID

from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.refund.application import refund_event_names as names


class RecordRejectedRefundUseCase:
    """Journalise une demande de remboursement refusée à la validation, avant le cas d'usage.

    Ni la valeur reçue, ni le nom d'un champ en trop, ni un identifiant mal formé n'entrent dans
    le journal : seule une raison en code et, si l'identifiant est un UUID, la ressource.
    """

    def __init__(self, events: BusinessEventLogger) -> None:
        self._events = events

    def execute(self, raw_intent_id: str) -> None:
        self._events.log(
            BusinessEvent.denied(
                names.REFUND_REJECTED,
                "invalid_request",
                resource_type="payment_intent",
                resource_id=self._known_id(raw_intent_id),
            )
        )

    @staticmethod
    def _known_id(raw_intent_id: str) -> str | None:
        try:
            return str(UUID(raw_intent_id))
        except ValueError:
            return None
