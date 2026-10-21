"""Worker de livraison des webhooks : `python -m app.webhook.presentation.worker_main`.

Un processus à part (service `payment-worker` de la pile), même image et même base que l'API.
Il s'arrête proprement sur SIGTERM ou SIGINT, après l'événement en cours.
"""

import signal
import sys
import threading
from types import FrameType

from app.core.config import Settings
from app.core.database import build_engine
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.core.logging_setup import install_log_redaction
from app.webhook.presentation.webhook_worker import WebhookWorker
from app.webhook.wiring import build_deliver_use_case

NOT_CONFIGURED = 2


def main() -> int:
    settings = Settings()
    if not settings.webhook_url or not settings.webhook_secrets:
        print(
            "Webhook non configuré : APP_WEBHOOK_URL et APP_WEBHOOK_SECRET sont requis.",
            file=sys.stderr,
        )
        return NOT_CONFIGURED
    install_log_redaction(settings)
    events = StructlogBusinessEventLogger(settings.service_name, sys.stdout)
    stop = threading.Event()

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    deliver = build_deliver_use_case(build_engine(settings), settings, events)
    WebhookWorker(deliver.execute, events, settings.webhook_poll_interval_seconds).run(stop.is_set)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
