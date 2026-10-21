import time
from collections.abc import Callable

from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.order_expiration.application.expire_unpaid_orders import ExpireUnpaidOrdersUseCase

EXPIRATION_FAILED = "order.expiration_failed"


def run_once(use_case: ExpireUnpaidOrdersUseCase, events: BusinessEventLogger) -> bool:
    """Un passage : une panne (base arrêtée…) est journalisée, jamais fatale. Renvoie le succès."""
    try:
        use_case.execute()
    except Exception:
        events.log(BusinessEvent.error(EXPIRATION_FAILED, "expiration_error"))
        return False
    return True


def run_forever(
    use_case: ExpireUnpaidOrdersUseCase,
    events: BusinessEventLogger,
    interval_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
    should_stop: Callable[[], bool] = lambda: False,
) -> None:
    """Boucle sans état : chaque passage relit tout en base; plusieurs instances se départagent."""
    while not should_stop():
        run_once(use_case, events)
        sleep(interval_seconds)
