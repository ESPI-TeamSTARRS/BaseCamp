from app.core.events import service_event_names as names
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.observability.domain.interfaces.request_metrics import RequestMetrics
from app.observability.domain.value_objects.request_key import RequestKey

UNMATCHED_ROUTE = "unmatched"
OTHER_METHOD = "OTHER"
KNOWN_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
# Sondes et collecte : comptées dans les métriques, mais pas journalisées quand elles réussissent.
QUIET_ROUTES = frozenset({"/health", "/health/ready", "/metrics"})
CLIENT_ERROR_FLOOR = 400
SERVER_ERROR_FLOOR = 500


class RecordRequestUseCase:
    """Compte la requête et journalise une ligne typée (route, statut, latence, appelant).

    La route est toujours le gabarit (`/payments/intents/{intent_id}`), jamais le chemin réel :
    ni identifiant, ni valeur de l'appelant n'arrivent dans un libellé de métrique ni dans le
    journal. L'identifiant de requête du journal est le `correlation_id` commun.
    """

    def __init__(self, metrics: RequestMetrics, events: BusinessEventLogger) -> None:
        self._metrics = metrics
        self._events = events

    def execute(
        self, route: str | None, method: str, status: int, seconds: float, caller: str | None
    ) -> None:
        label = route or UNMATCHED_ROUTE
        known_method = method if method in KNOWN_METHODS else OTHER_METHOD
        self._metrics.observe(RequestKey(label, known_method, status), seconds)
        if label in QUIET_ROUTES and status < CLIENT_ERROR_FLOOR:
            return
        self._events.log(self._event(label, known_method, status, seconds, caller))

    @staticmethod
    def _event(
        route: str, method: str, status: int, seconds: float, caller: str | None
    ) -> BusinessEvent:
        fields: dict[str, object] = {
            "duration_ms": int(seconds * 1000),
            "attributes": {"route": route, "method": method, "status": status},
        }
        if caller:
            fields["actor_type"] = "service"
            fields["actor_id"] = caller
        if status < CLIENT_ERROR_FLOOR:
            return BusinessEvent.success(names.REQUEST_COMPLETED, **fields)
        if status < SERVER_ERROR_FLOOR:
            return BusinessEvent.denied(names.REQUEST_COMPLETED, f"http_{status}", **fields)
        return BusinessEvent.error(names.REQUEST_COMPLETED, f"http_{status}", **fields)
