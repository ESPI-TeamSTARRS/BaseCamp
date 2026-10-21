from datetime import UTC, datetime

from sqlalchemy import Engine

from app.core.config import Settings
from app.core.events.business_event_logger import BusinessEventLogger
from app.expiration.application.expiration_services import ExpirationServices
from app.expiration.application.expire_unconfirmed_intents import ExpireUnconfirmedIntentsUseCase
from app.expiration.infrastructure.repositories.sqlalchemy_intent_expiry_repository import (
    SqlAlchemyIntentExpiryRepository,
)


def build_expiration_services(
    engine: Engine, settings: Settings, events: BusinessEventLogger
) -> ExpirationServices:
    """Assemble le traitement d'expiration avec son adaptateur de base de données."""
    return ExpirationServices(
        expire=ExpireUnconfirmedIntentsUseCase(
            SqlAlchemyIntentExpiryRepository(engine),
            lambda: datetime.now(UTC),
            settings.expiration_batch_size,
            events,
        )
    )
