"""Commande d'exploitation : relancer les webhooks `dead`.

    python -m app.webhook.presentation.requeue_main --event-id <uuid>
    python -m app.webhook.presentation.requeue_main --all

L'événement garde son identifiant et son corps : la boutique le déduplique, sans second effet.
"""

import argparse
import sys
from collections.abc import Sequence
from typing import TextIO
from uuid import UUID

from app.core.config import Settings
from app.core.database import build_engine
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.webhook.application.requeue_dead_events import RequeueDeadEventsUseCase
from app.webhook.wiring import build_requeue_use_case


def run(argv: Sequence[str], use_case: RequeueDeadEventsUseCase, out: TextIO) -> int:
    parser = argparse.ArgumentParser(prog="requeue_main", description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--event-id", type=UUID, help="identifiant de l'événement à relancer")
    target.add_argument("--all", action="store_true", help="relance tous les événements dead")
    arguments = parser.parse_args(argv)
    count = use_case.execute(None if arguments.all else arguments.event_id)
    if count == 0:
        print("Aucun événement dead à relancer.", file=out)
        return 1
    print(f"{count} événement(s) relancé(s).", file=out)
    return 0


def main() -> int:
    settings = Settings()
    events = StructlogBusinessEventLogger(settings.service_name, sys.stdout)
    return run(sys.argv[1:], build_requeue_use_case(build_engine(settings), events), sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
