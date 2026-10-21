"""Point d'entrée du traitement d'expiration : `python -m app.expiration.presentation.cli`.

Passage unique, sans état : à lancer périodiquement (planificateur, tâche cron, `docker compose
exec`). Plusieurs instances en parallèle sont sans danger (verrous de ligne, `SKIP LOCKED`).
"""

import sys

from sqlalchemy import Engine

from app.core.config import Settings
from app.core.database import build_engine
from app.core.events.business_event_logger import BusinessEventLogger
from app.core.logging.correlation import new_correlation_id, set_correlation_id
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.core.logging_setup import install_log_redaction
from app.expiration.wiring import build_expiration_services


def main(
    settings: Settings | None = None,
    engine: Engine | None = None,
    events: BusinessEventLogger | None = None,
) -> int:
    settings = settings or Settings()
    engine = engine or build_engine(settings)
    events = events or StructlogBusinessEventLogger(settings.service_name, sys.stdout)
    install_log_redaction(settings)
    set_correlation_id(new_correlation_id())  # une corrélation par passage
    build_expiration_services(engine, settings, events).expire.execute()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
