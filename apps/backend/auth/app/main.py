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
    application.include_router(health_router)
    register_error_handlers(application, events)
    return application


app = create_app()
