"""Commande `ledger-check` : `python -m app.ledgercheck.presentation.cli` (ou `uv run poe ledger-check`).

Passage unique, en lecture seule, sans état : à lancer périodiquement (planificateur, tâche cron,
`docker compose exec payment ...`). Plusieurs passages en parallèle sont sans danger.

Codes de sortie : 0 grand livre cohérent, 1 écarts constatés, 2 contrôle impossible (base
indisponible). Le rapport est écrit sur la sortie standard, après les lignes de journal JSON.
"""

import sys
from typing import TextIO

from sqlalchemy import Engine

from app.core.config import Settings
from app.core.database import build_engine
from app.core.events.business_event_logger import BusinessEventLogger
from app.core.logging.correlation import new_correlation_id, set_correlation_id
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.core.logging_setup import install_log_redaction
from app.ledgercheck.application.exceptions.ledger_check_unavailable_error import (
    LedgerCheckUnavailableError,
)
from app.ledgercheck.presentation.ledger_check_report_renderer import LedgerCheckReportRenderer
from app.ledgercheck.wiring import build_ledger_check_services

EXIT_CONSISTENT = 0
EXIT_DISCREPANCIES = 1
EXIT_UNAVAILABLE = 2


def main(
    settings: Settings | None = None,
    engine: Engine | None = None,
    events: BusinessEventLogger | None = None,
    out: TextIO | None = None,
) -> int:
    settings = settings or Settings()
    engine = engine or build_engine(settings)
    events = events or StructlogBusinessEventLogger(settings.service_name, sys.stdout)
    out = out or sys.stdout
    install_log_redaction(settings)
    set_correlation_id(new_correlation_id())  # une corrélation par passage
    try:
        report = build_ledger_check_services(engine, events).check.execute()
    except LedgerCheckUnavailableError:
        print("contrôle impossible : base de données indisponible", file=out)
        return EXIT_UNAVAILABLE
    print(LedgerCheckReportRenderer().render(report), file=out)
    return EXIT_CONSISTENT if report.is_consistent else EXIT_DISCREPANCIES


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
