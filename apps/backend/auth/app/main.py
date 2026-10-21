import sys
from typing import TextIO

from fastapi import FastAPI
from sqlalchemy import Engine, create_engine

from app.admin.composition import wire_admin
from app.admin.presentation.error_handlers import register_admin_error_handlers
from app.admin.presentation.router import router as admin_router
from app.core.config import Settings
from app.core.errors import register_error_handlers
from app.core.logging.correlation_id_middleware import CorrelationIdMiddleware
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.health.application.get_readiness import GetReadinessUseCase
from app.health.infrastructure.clients.sqlalchemy_database_probe import SqlAlchemyDatabaseProbe
from app.health.presentation.router import router as health_router
from app.login.composition import wire_login
from app.login.presentation.error_handlers import register_login_error_handlers
from app.login.presentation.router import router as login_router
from app.login.presentation.well_known_router import router as well_known_router
from app.observability.presentation.request_observer_middleware import RequestObserverMiddleware
from app.observability.presentation.router import router as observability_router
from app.observability.wiring import build_observability
from app.password_reset.composition import wire_password_reset
from app.password_reset.presentation.error_handlers import register_password_reset_error_handlers
from app.password_reset.presentation.router import router as password_reset_router
from app.registration.composition import wire_registration
from app.registration.presentation.error_handlers import register_registration_error_handlers
from app.registration.presentation.router import router as registration_router
from app.service_token.error_handlers import (
    register_error_handlers as register_service_token_error_handlers,
)
from app.service_token.presentation.router import router as service_token_router
from app.service_token.wiring import build_service_token_services

DB_CONNECT_TIMEOUT_SECONDS = 2


def create_app(
    settings: Settings | None = None,
    engine: Engine | None = None,
    journal_stream: TextIO | None = None,
) -> FastAPI:
    """Assemble le service. Les parametres ne servent qu'aux tests (base, configuration, sortie du journal)."""
    settings = settings or Settings()
    engine = engine or create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": DB_CONNECT_TIMEOUT_SECONDS},
    )
    journal = StructlogBusinessEventLogger(settings.service_name, journal_stream or sys.stdout)
    observability = build_observability(engine, settings, journal)
    events = observability.events  # journal + compteurs : un seul evenement alimente les deux
    application = FastAPI(title="basecamp-auth")
    # Le dernier ajoute est le plus externe : correlation, puis observation de la requete.
    application.add_middleware(
        RequestObserverMiddleware, record=observability.services.record_request
    )
    application.add_middleware(CorrelationIdMiddleware)
    application.state.observability_services = observability.services
    application.state.events = events
    application.state.readiness_use_case = GetReadinessUseCase(
        settings.service_name, SqlAlchemyDatabaseProbe(engine)
    )
    application.state.service_token_services = build_service_token_services(
        engine, settings, events
    )
    wire_registration(application, settings, engine, events)
    wire_password_reset(application, settings, engine, events)
    wire_login(application, settings, engine, events)
    wire_admin(application, engine, events)
    application.include_router(health_router)
    application.include_router(observability_router)
    application.include_router(service_token_router)
    application.include_router(registration_router)
    application.include_router(password_reset_router)
    application.include_router(login_router)
    application.include_router(well_known_router)
    application.include_router(admin_router)
    register_error_handlers(application, events)
    register_service_token_error_handlers(application)
    register_registration_error_handlers(application)
    register_password_reset_error_handlers(application)
    register_login_error_handlers(application)
    register_admin_error_handlers(application)
    return application


app = create_app()
