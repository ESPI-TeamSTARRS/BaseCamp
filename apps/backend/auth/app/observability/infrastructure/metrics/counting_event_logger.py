from collections.abc import Collection

from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.observability.domain.interfaces.request_metrics import RequestMetrics
from app.observability.domain.value_objects.event_key import EventKey

UNKNOWN_CLIENT = "unknown"
NO_DETAIL = ""
# Evenement -> attribut qui sert de detail (code ferme). Les autres evenements n'ont pas de detail.
DETAIL_ATTRIBUTE = {
    "auth.login_failed": "cause",
    "auth.refresh_rejected": "cause",
    "auth.lockout_triggered": "step",
}
# Evenements dont le detail est le client de service (`resource_id`), borne aux clients connus.
CLIENT_EVENTS = frozenset({"auth.service_token_denied", "auth.service_rate_limited"})


class CountingEventLogger(BusinessEventLogger):
    """Journalise l'evenement puis le compte : les signaux sortent des memes evenements que le journal.

    Une seule source (l'evenement metier) alimente le journal et la metrique, donc ils ne divergent
    pas. Aucun libelle ne vient d'une saisie de l'appelant : un nom de client absent de la
    configuration est compte sous `unknown`.
    """

    def __init__(
        self,
        delegate: BusinessEventLogger,
        metrics: RequestMetrics,
        known_clients: Collection[str],
    ) -> None:
        self._delegate = delegate
        self._metrics = metrics
        self._known_clients = frozenset(known_clients)

    def log(self, event: BusinessEvent) -> None:
        self._delegate.log(event)
        self._metrics.count_event(
            EventKey(
                event.event, event.outcome.value, event.reason or NO_DETAIL, self._detail(event)
            )
        )

    def _detail(self, event: BusinessEvent) -> str:
        if event.event in CLIENT_EVENTS:
            client = event.resource_id or NO_DETAIL
            return client if client in self._known_clients else UNKNOWN_CLIENT
        attribute = DETAIL_ATTRIBUTE.get(event.event)
        value = event.attributes.get(attribute) if attribute else None
        return str(value) if isinstance(value, str) else NO_DETAIL
