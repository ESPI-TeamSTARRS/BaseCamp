from datetime import timedelta

from sqlalchemy import Engine

from app.core.config import Settings
from app.core.events.business_event_logger import BusinessEventLogger
from app.lockout.application.lockout_service import LockoutService
from app.lockout.application.lockout_steps import (
    STEP_FACE,
    STEP_INVITATION,
    STEP_OPERATOR_PASSWORD,
)
from app.lockout.domain.entities.lockout_policies import LockoutPolicies
from app.lockout.domain.entities.lockout_policy import LockoutPolicy
from app.lockout.domain.enums.subject_type import SubjectType
from app.lockout.infrastructure.repositories.sqlalchemy_lockout_unit_of_work import (
    SqlAlchemyLockoutUnitOfWork,
)


def build_lockout_policy(settings: Settings) -> LockoutPolicy:
    """Politique progressive par defaut (etapes existantes) lue de la configuration."""
    return LockoutPolicy(
        max_failures=settings.lockout_max_failures,
        window=timedelta(seconds=settings.lockout_window_seconds),
        durations=tuple(timedelta(seconds=value) for value in settings.lockout_durations),
        memory=timedelta(seconds=settings.lockout_memory_seconds),
    )


def _fixed(max_failures: int, window_seconds: int, duration_seconds: int) -> LockoutPolicy:
    """Blocage de duree fixe, sans escalade (la memoire est la duree du blocage)."""
    duration = timedelta(seconds=duration_seconds)
    return LockoutPolicy(
        max_failures=max_failures,
        window=timedelta(seconds=window_seconds),
        durations=(duration,),
        memory=duration,
    )


def build_lockout_policies(settings: Settings) -> LockoutPolicies:
    """Regle par etape : aucun seuil n'est code dans les etapes appelantes."""
    return LockoutPolicies(
        default=build_lockout_policy(settings),
        address=_fixed(
            settings.lockout_address_max_failures,
            settings.lockout_address_window_seconds,
            settings.lockout_address_duration_seconds,
        ),
        steps={
            (STEP_OPERATOR_PASSWORD, SubjectType.ACCOUNT): _fixed(
                settings.lockout_operator_password_max_failures,
                settings.lockout_operator_password_window_seconds,
                settings.lockout_operator_password_duration_seconds,
            ),
            (STEP_INVITATION, SubjectType.SOURCE_ADDRESS): _fixed(
                settings.lockout_invitation_max_failures,
                settings.lockout_invitation_window_seconds,
                settings.lockout_invitation_duration_seconds,
            ),
            (STEP_FACE, SubjectType.ACCOUNT): _fixed(
                settings.lockout_face_max_failures,
                settings.lockout_face_window_seconds,
                settings.lockout_face_duration_seconds,
            ),
        },
    )


def build_lockout_service(
    settings: Settings, engine: Engine, events: BusinessEventLogger
) -> LockoutService:
    """Seul endroit qui assemble les implementations d'infrastructure de la tranche."""
    return LockoutService(
        lambda: SqlAlchemyLockoutUnitOfWork(engine), build_lockout_policies(settings), events
    )
