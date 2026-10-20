from fastapi import FastAPI
from sqlalchemy import create_engine

from app.cart.application.quote_cart import QuoteCartUseCase
from app.cart.infrastructure.repositories.sqlalchemy_cart_product_reader import (
    SqlAlchemyCartProductReader,
)
from app.cart.presentation.router import router as cart_router
from app.catalog.application.get_product import GetProductUseCase
from app.catalog.application.list_products import ListProductsUseCase
from app.catalog.infrastructure.repositories.sqlalchemy_product_repository import (
    SqlAlchemyProductRepository,
)
from app.catalog.presentation.router import router as catalog_router
from app.core.config import Settings
from app.core.errors import register_error_handlers
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
    application = FastAPI(title="basecamp-shop")
    application.state.readiness_use_case = GetReadinessUseCase(
        settings.service_name, SqlAlchemyDatabaseProbe(engine)
    )
    application.state.list_products_use_case = ListProductsUseCase(
        SqlAlchemyProductRepository(engine)
    )
    application.state.get_product_use_case = GetProductUseCase(SqlAlchemyProductRepository(engine))
    application.state.quote_cart_use_case = QuoteCartUseCase(SqlAlchemyCartProductReader(engine))
    register_error_handlers(application)
    application.include_router(health_router)
    application.include_router(catalog_router)
    application.include_router(cart_router)
    return application


app = create_app()
