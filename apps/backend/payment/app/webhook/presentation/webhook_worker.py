import time
from collections.abc import Callable

from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.webhook.application import webhook_event_names as names


class WebhookWorker:
    """Boucle de livraison : enchaîne les événements échus, dort quand il n'y en a plus.

    Une panne de la base ou de la boutique ne l'arrête jamais : l'erreur est journalisée (sans
    message d'exception, qui pourrait contenir une valeur sensible) puis la boucle reprend.
    """

    def __init__(
        self,
        deliver: Callable[[], bool],
        events: BusinessEventLogger,
        poll_interval_seconds: float,
        wait: Callable[[float], None] = time.sleep,
    ) -> None:
        self._deliver = deliver
        self._events = events
        self._poll_interval = poll_interval_seconds
        self._wait = wait

    def run(self, should_stop: Callable[[], bool]) -> None:
        while not should_stop():
            try:
                handled = self._deliver()
            except Exception:
                self._events.log(BusinessEvent.error(names.WEBHOOK_WORKER_FAILED, "worker_error"))
                handled = False
            if not handled:
                self._wait(self._poll_interval)
