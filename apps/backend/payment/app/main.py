from fastapi import FastAPI
from sqlalchemy import create_engine

from app.core.config import Settings
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
    application = FastAPI(title="basecamp-payment")
    application.state.readiness_use_case = GetReadinessUseCase(
        settings.service_name, SqlAlchemyDatabaseProbe(engine)
    )
    application.include_router(health_router)
    return application


app = create_app()
