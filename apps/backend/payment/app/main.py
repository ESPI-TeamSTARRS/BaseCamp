from fastapi import FastAPI
from sqlalchemy import create_engine

from app.core.config import Settings
from app.health.application.get_readiness import GetReadinessUseCase
from app.health.infrastructure.clients.sqlalchemy_database_probe import SqlAlchemyDatabaseProbe
from app.health.presentation.router import router as health_router
from app.intent.error_handlers import register_error_handlers
from app.intent.presentation.router import router as intent_router
from app.intent.wiring import build_intent_services

DB_CONNECT_TIMEOUT_SECONDS = 2


def create_app() -> FastAPI:
    settings = Settings()
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": DB_CONNECT_TIMEOUT_SECONDS},
    )
    application = FastAPI(title="basecamp-payment")
    application.state.readiness_use_case = GetReadinessUseCase(
        settings.service_name, SqlAlchemyDatabaseProbe(engine)
    )
    application.state.intent_services = build_intent_services(engine, settings)
    application.include_router(health_router)
    application.include_router(intent_router)
    register_error_handlers(application)
    return application


app = create_app()
