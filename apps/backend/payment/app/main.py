import sys

from fastapi import FastAPI
from sqlalchemy import Engine

from app.cancellation.error_handlers import register_cancellation_error_handlers
from app.cancellation.presentation.router import router as cancellation_router
from app.cancellation.wiring import build_cancellation_services
from app.confirmation.error_handlers import register_confirmation_error_handlers
from app.confirmation.presentation.router import router as confirmation_router
from app.confirmation.wiring import build_confirmation_services
from app.core.config import Settings
from app.core.database import build_engine
from app.core.errors import register_database_unavailable_handler, register_unhandled_error_handler
from app.core.events.business_event_logger import BusinessEventLogger
from app.core.http.body_size_limit_middleware import BodySizeLimitMiddleware
from app.core.http.concurrency_limit_middleware import ConcurrencyLimitMiddleware
from app.core.http.request_timeout_middleware import RequestTimeoutMiddleware
from app.core.logging.correlation_id_middleware import CorrelationIdMiddleware
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.core.logging_setup import install_log_redaction
from app.health.application.get_health import GetHealthUseCase
from app.health.application.get_readiness import GetReadinessUseCase
from app.health.infrastructure.clients.sqlalchemy_database_probe import SqlAlchemyDatabaseProbe
from app.health.presentation.router import router as health_router
from app.intent.error_handlers import register_error_handlers
from app.intent.presentation.router import router as intent_router
from app.intent.wiring import build_intent_services
from app.observability.presentation.request_observer_middleware import RequestObserverMiddleware
from app.observability.presentation.router import router as observability_router
from app.observability.wiring import build_observability_services
from app.ratelimit.error_handlers import register_rate_limit_error_handlers
from app.ratelimit.wiring import build_rate_limiter


def create_app(
    settings: Settings | None = None,
    engine: Engine | None = None,
    events: BusinessEventLogger | None = None,
) -> FastAPI:
    settings = settings or Settings()
    engine = engine or build_engine(settings)
    events = events or StructlogBusinessEventLogger(settings.service_name, sys.stdout)
    install_log_redaction(settings)
    application = FastAPI(title="basecamp-payment")
    application.state.events = events
    application.state.health_use_case = GetHealthUseCase(settings.service_name)
    application.state.readiness_use_case = GetReadinessUseCase(
        settings.service_name, SqlAlchemyDatabaseProbe(engine)
    )
    application.state.intent_services = build_intent_services(engine, settings, events)
    application.state.confirmation_services = build_confirmation_services(engine, settings, events)
    application.state.cancellation_services = build_cancellation_services(engine, events)
    application.state.rate_limiter = build_rate_limiter(engine, settings, events)
    observability = build_observability_services(engine, settings, events)
    application.state.observability_services = observability
    application.include_router(health_router)
    application.include_router(observability_router)
    application.include_router(intent_router)
    application.include_router(confirmation_router)
    application.include_router(cancellation_router)
    register_error_handlers(application, events)
    register_confirmation_error_handlers(application)
    register_cancellation_error_handlers(application)
    register_rate_limit_error_handlers(application)
    register_database_unavailable_handler(application, events)
    register_unhandled_error_handler(application, events)
    # Le dernier ajouté est le plus externe : corrélation, observation (voit aussi les 503 et 504),
    # concurrence, délais, taille du corps.
    application.add_middleware(
        BodySizeLimitMiddleware, max_bytes=settings.max_body_bytes, events=events
    )
    application.add_middleware(
        RequestTimeoutMiddleware,
        read_timeout=settings.read_timeout_seconds,
        write_timeout=settings.write_timeout_seconds,
        request_timeout=settings.request_timeout_seconds,
        events=events,
    )
    application.add_middleware(
        ConcurrencyLimitMiddleware, max_concurrent=settings.max_concurrent_requests, events=events
    )
    application.add_middleware(RequestObserverMiddleware, record=observability.record_request)
    application.add_middleware(CorrelationIdMiddleware)
    return application


app = create_app()
