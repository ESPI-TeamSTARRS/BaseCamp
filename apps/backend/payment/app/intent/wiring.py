from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine

from app.caller_identity.domain.interfaces.jwks_source import JwksSource
from app.caller_identity.wiring import build_authenticate_caller
from app.core.config import Settings
from app.core.events.business_event_logger import BusinessEventLogger
from app.intent.application.create_payment_intent import CreatePaymentIntentUseCase
from app.intent.application.get_payment_intent import GetPaymentIntentUseCase
from app.intent.application.get_payment_intent_by_order import GetPaymentIntentByOrderUseCase
from app.intent.application.intent_services import IntentServices
from app.intent.infrastructure.repositories.sqlalchemy_payment_intent_repository import (
    SqlAlchemyPaymentIntentRepository,
)


def build_intent_services(
    engine: Engine,
    settings: Settings,
    events: BusinessEventLogger,
    jwks_source: JwksSource | None = None,
) -> IntentServices:
    """Assemble les cas d'usage de la tranche avec leurs adaptateurs d'infrastructure."""
    repository = SqlAlchemyPaymentIntentRepository(engine)
    return IntentServices(
        authenticate=build_authenticate_caller(settings, events, jwks_source),
        create=CreatePaymentIntentUseCase(
            repository,
            lambda: datetime.now(UTC),
            timedelta(minutes=settings.intent_ttl_minutes),
            settings.max_amount_cents,
            events,
        ),
        get_by_id=GetPaymentIntentUseCase(repository, events),
        get_by_order=GetPaymentIntentByOrderUseCase(repository, events),
    )
