from typing import Protocol

from app.core.events.business_event import BusinessEvent


class BusinessEventLogger(Protocol):
    """Port de journalisation metier : les cas d'usage y emettent leurs evenements."""

    def log(self, event: BusinessEvent) -> None: ...
