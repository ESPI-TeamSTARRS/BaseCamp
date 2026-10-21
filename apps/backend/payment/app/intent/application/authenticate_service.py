import hmac

from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.intent.application.exceptions.unauthorized_service_error import UnauthorizedServiceError

AUTHENTICATED_EVENT = "payment.service_authenticated"


class AuthenticateServiceUseCase:
    """Identifie l'appelant par son jeton statique (comparaison en temps constant)."""

    def __init__(self, tokens_by_caller: dict[str, str], events: BusinessEventLogger) -> None:
        self._tokens_by_caller = tokens_by_caller
        self._events = events

    def execute(self, token: str | None, client_ip: str | None = None) -> str:
        candidate = (token or "").encode()
        caller: str | None = None
        for name, expected in self._tokens_by_caller.items():
            # Tous les jetons sont comparés : pas de sortie anticipée qui trahirait un appelant.
            matches = hmac.compare_digest(candidate, expected.encode())
            if matches and candidate and caller is None:
                caller = name
        if caller is None:
            self._events.log(
                BusinessEvent.denied(AUTHENTICATED_EVENT, "invalid_token", client_ip=client_ip)
            )
            raise UnauthorizedServiceError
        self._events.log(
            BusinessEvent.success(AUTHENTICATED_EVENT, actor_type="service", actor_id=caller)
        )
        return caller
