from uuid import UUID

from app.confirmation.application import confirmation_event_names as names
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger


class RecordRejectedConfirmationUseCase:
    """Journalise une demande refusée à la validation, avant d'atteindre le cas d'usage.

    Ni la valeur reçue, ni le nom d'un champ en trop, ni un identifiant mal formé n'entrent dans
    le journal : seule une raison en code et, si l'identifiant est un UUID, la ressource.
    """

    def __init__(self, events: BusinessEventLogger) -> None:
        self._events = events

    def execute(self, raw_intent_id: str, invalid_method: bool) -> None:
        self._events.log(
            BusinessEvent.denied(
                names.PAYMENT_CONFIRMATION_REJECTED,
                "invalid_payment_method" if invalid_method else "invalid_request",
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
