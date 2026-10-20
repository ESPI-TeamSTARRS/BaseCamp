"""Doublure du port de journalisation : garde les evenements emis (pas un test)."""

from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger


class InMemoryBusinessEventLogger(BusinessEventLogger):
    def __init__(self) -> None:
        self.events: list[BusinessEvent] = []

    def log(self, event: BusinessEvent) -> None:
        self.events.append(event)
