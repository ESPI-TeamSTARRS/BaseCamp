import sys

from fastapi import FastAPI
from sqlalchemy import create_engine

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


def create_app() -> FastAPI:
    settings = Settings()
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": DB_CONNECT_TIMEOUT_SECONDS},
    )
    events = StructlogBusinessEventLogger(settings.service_name, sys.stdout)
    application = FastAPI(title="basecamp-auth")
    application.add_middleware(CorrelationIdMiddleware)
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
    application.include_router(health_router)
    application.include_router(service_token_router)
    application.include_router(registration_router)
    application.include_router(password_reset_router)
    application.include_router(login_router)
    application.include_router(well_known_router)
    register_error_handlers(application, events)
    register_service_token_error_handlers(application)
    register_registration_error_handlers(application)
    register_password_reset_error_handlers(application)
    register_login_error_handlers(application)
    return application


app = create_app()
