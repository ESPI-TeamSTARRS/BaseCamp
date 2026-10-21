"""Traitement d'expiration déclenchable : `python -m app.order_expiration [--once | --every SECONDES]`."""

import argparse
import sys
from datetime import UTC, datetime

from sqlalchemy import create_engine

from app.core.config import Settings
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.order_expiration.application.expire_unpaid_orders import ExpireUnpaidOrdersUseCase
from app.order_expiration.infrastructure.repositories.sqlalchemy_expiration_unit_of_work import (
    SqlAlchemyExpirationUnitOfWork,
)
from app.order_expiration.runner import run_forever, run_once

DEFAULT_INTERVAL_SECONDS = 60.0
DB_CONNECT_TIMEOUT_SECONDS = 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Expire les commandes impayées et rend le stock.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--once", action="store_true", help="un seul passage (défaut)")
    group.add_argument(
        "--every",
        type=float,
        metavar="SECONDES",
        help=f"boucle sans état, un passage toutes les N secondes (ex. {DEFAULT_INTERVAL_SECONDS:.0f})",
    )
    arguments = parser.parse_args(argv)
    settings = Settings()
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": DB_CONNECT_TIMEOUT_SECONDS},
    )
    events = StructlogBusinessEventLogger(settings.service_name, sys.stdout)
    use_case = ExpireUnpaidOrdersUseCase(
        lambda: SqlAlchemyExpirationUnitOfWork(engine),
        events,
        clock=lambda: datetime.now(UTC),
        ttl_minutes=settings.order_expiration_minutes,
    )
    if arguments.every is not None:
        run_forever(use_case, events, arguments.every)
        return 0
    return 0 if run_once(use_case, events) else 1


if __name__ == "__main__":
    raise SystemExit(main())
