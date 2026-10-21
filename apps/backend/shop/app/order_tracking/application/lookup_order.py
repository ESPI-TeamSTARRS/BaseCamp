import hmac

from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.order.domain.interfaces.email_pseudonymizer import EmailPseudonymizer
from app.order_tracking.application.order_lookup_failed_error import OrderLookupFailedError
from app.order_tracking.domain.entities.tracked_order import TrackedOrder
from app.order_tracking.domain.interfaces.tracked_order_reader import TrackedOrderReader

LOOKED_UP = "order.looked_up"
LOOKUP_DENIED = "order.lookup_denied"
_NO_EMAIL = "\x00"  # comparé à l'email reçu quand le numéro est inconnu, pour un travail équivalent


class LookupOrderUseCase:
    """Retrouve une commande par numéro et email, sans permettre d'énumérer les commandes.

    Numéro inconnu et email erroné lèvent la même erreur; seuls les logs internes les distinguent.
    """

    def __init__(
        self,
        reader: TrackedOrderReader,
        events: BusinessEventLogger,
        pseudonymizer: EmailPseudonymizer,
    ) -> None:
        self._reader = reader
        self._events = events
        self._pseudonymizer = pseudonymizer

    def execute(self, number: str, email: str) -> TrackedOrder:
        order = self._reader.find_by_number(number)
        stored = order.email if order is not None else _NO_EMAIL
        matches = hmac.compare_digest(self._normalise(stored), self._normalise(email))
        if order is None or not matches:
            self._deny(number if order is not None else None, email, order is None)
            raise OrderLookupFailedError
        self._events.log(
            BusinessEvent.success(
                LOOKED_UP,
                resource_type="order",
                resource_id=order.number,
                attributes={"status": order.status},
            )
        )
        return order

    @staticmethod
    def _normalise(email: str) -> bytes:
        return email.strip().casefold().encode("utf-8")

    def _deny(self, number: str | None, email: str, unknown: bool) -> None:
        attributes = {"email_hash": self._pseudonymizer.pseudonymize(email)}
        reason = "order_not_found" if unknown else "email_mismatch"
        if number is None:
            self._events.log(BusinessEvent.denied(LOOKUP_DENIED, reason, attributes=attributes))
            return
        self._events.log(
            BusinessEvent.denied(
                LOOKUP_DENIED,
                reason,
                resource_type="order",
                resource_id=number,
                attributes=attributes,
            )
        )
