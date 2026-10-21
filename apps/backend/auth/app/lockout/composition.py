from datetime import timedelta

from sqlalchemy import Engine

from app.core.config import Settings
from app.core.events.business_event_logger import BusinessEventLogger
from app.lockout.application.lockout_service import LockoutService
from app.lockout.domain.entities.lockout_policy import LockoutPolicy
from app.lockout.infrastructure.repositories.sqlalchemy_lockout_unit_of_work import (
    SqlAlchemyLockoutUnitOfWork,
)


def build_lockout_policy(settings: Settings) -> LockoutPolicy:
    """Politique lue de la configuration : aucun seuil n'est code dans les etapes appelantes."""
    return LockoutPolicy(
        max_failures=settings.lockout_max_failures,
        window=timedelta(seconds=settings.lockout_window_seconds),
        durations=tuple(timedelta(seconds=value) for value in settings.lockout_durations),
        memory=timedelta(seconds=settings.lockout_memory_seconds),
    )


def build_lockout_service(
    settings: Settings, engine: Engine, events: BusinessEventLogger
) -> LockoutService:
    """Seul endroit qui assemble les implementations d'infrastructure de la tranche."""
    return LockoutService(
        lambda: SqlAlchemyLockoutUnitOfWork(engine), build_lockout_policy(settings), events
    )
