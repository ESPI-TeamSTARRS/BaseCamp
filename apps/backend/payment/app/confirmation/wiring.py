import time
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import Engine

from app.confirmation.application.confirm_payment import ConfirmPaymentUseCase
from app.confirmation.application.confirmation_services import ConfirmationServices
from app.confirmation.application.record_rejected_confirmation import (
    RecordRejectedConfirmationUseCase,
)
from app.confirmation.infrastructure.providers.internal_payment_provider import (
    InternalPaymentProvider,
)
from app.confirmation.infrastructure.repositories.sqlalchemy_confirmation_unit_of_work import (
    SqlAlchemyConfirmationUnitOfWork,
)
from app.core.config import Settings
from app.core.events.business_event_logger import BusinessEventLogger


def build_confirmation_services(
    engine: Engine,
    settings: Settings,
    events: BusinessEventLogger,
    wait: Callable[[float], None] = time.sleep,
) -> ConfirmationServices:
    """Assemble les cas d'usage avec le fournisseur interne (le seul branché aujourd'hui)."""
    return ConfirmationServices(
        confirm=ConfirmPaymentUseCase(
            SqlAlchemyConfirmationUnitOfWork(engine),
            InternalPaymentProvider(wait, settings.provider_timeout_seconds),
            lambda: datetime.now(UTC),
            events,
        ),
        record_rejection=RecordRejectedConfirmationUseCase(events),
    )
