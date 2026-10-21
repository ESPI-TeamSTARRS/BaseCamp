from datetime import UTC, datetime

from sqlalchemy import Engine

from app.cancellation.application.cancel_payment_intent import CancelPaymentIntentUseCase
from app.cancellation.application.cancellation_services import CancellationServices
from app.cancellation.infrastructure.repositories.sqlalchemy_cancellation_unit_of_work import (
    SqlAlchemyCancellationUnitOfWork,
)
from app.core.events.business_event_logger import BusinessEventLogger


def build_cancellation_services(
    engine: Engine, events: BusinessEventLogger
) -> CancellationServices:
    """Assemble le cas d'usage d'annulation avec son adaptateur de base de données."""
    return CancellationServices(
        cancel=CancelPaymentIntentUseCase(
            SqlAlchemyCancellationUnitOfWork(engine), lambda: datetime.now(UTC), events
        )
    )
