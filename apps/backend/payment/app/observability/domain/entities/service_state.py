from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceState:
    """Etat metier lu en base a la demande (jamais conserve en memoire entre deux lectures)."""

    intents_by_status: Mapping[str, int]
    webhook_events_by_status: Mapping[str, int]
    webhook_oldest_pending_age_seconds: float
    captured_amount_cents: int
    refunded_amount_cents: int
    refunded_intents: int
    ledger_discrepancies: Mapping[str, int]
