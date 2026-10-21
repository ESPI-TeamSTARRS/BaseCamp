import sys

import httpx
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
from app.core.logging.correlation_id_middleware import CorrelationIdMiddleware
from app.core.logging.email_pseudonymizer import build_pseudonymizer
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.health.application.get_readiness import GetReadinessUseCase
from app.health.infrastructure.clients.sqlalchemy_database_probe import SqlAlchemyDatabaseProbe
from app.health.presentation.router import router as health_router
from app.order.application.place_order import PlaceOrderUseCase
from app.order.infrastructure.repositories.sqlalchemy_order_unit_of_work import (
    SqlAlchemyOrderUnitOfWork,
)
from app.order.presentation.router import router as order_router
from app.order_tracking.application.lookup_order import LookupOrderUseCase
from app.order_tracking.infrastructure.repositories.sqlalchemy_tracked_order_reader import (
    SqlAlchemyTrackedOrderReader,
)
from app.order_tracking.presentation.router import router as order_tracking_router
from app.pay.application.start_payment import StartPaymentUseCase
from app.pay.error_handlers import register_pay_error_handlers
from app.pay.infrastructure.clients.http_payment_gateway import HttpPaymentGateway
from app.pay.presentation.router import router as pay_router

DB_CONNECT_TIMEOUT_SECONDS = 2


def create_app() -> FastAPI:
    settings = Settings()
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": DB_CONNECT_TIMEOUT_SECONDS},
    )
    events = StructlogBusinessEventLogger(settings.service_name, sys.stdout)
    application = FastAPI(title="basecamp-shop")
    application.add_middleware(CorrelationIdMiddleware)
    application.state.events = events
    application.state.readiness_use_case = GetReadinessUseCase(
        settings.service_name, SqlAlchemyDatabaseProbe(engine)
    )
    application.state.list_products_use_case = ListProductsUseCase(
        SqlAlchemyProductRepository(engine), events
    )
    application.state.get_product_use_case = GetProductUseCase(
        SqlAlchemyProductRepository(engine), events
    )
    application.state.quote_cart_use_case = QuoteCartUseCase(
        SqlAlchemyCartProductReader(engine), events
    )
    application.state.place_order_use_case = PlaceOrderUseCase(
        lambda: SqlAlchemyOrderUnitOfWork(engine),
        events,
        build_pseudonymizer(settings.log_pseudonym_key),
    )
    application.state.lookup_order_use_case = LookupOrderUseCase(
        SqlAlchemyTrackedOrderReader(engine),
        events,
        build_pseudonymizer(settings.log_pseudonym_key),
    )
    payment_client = httpx.Client(
        base_url=settings.payment_url,
        timeout=httpx.Timeout(
            connect=settings.payment_connect_timeout_seconds,
            read=settings.payment_read_timeout_seconds,
            write=settings.payment_read_timeout_seconds,
            pool=settings.payment_connect_timeout_seconds,
        ),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=5),
    )
    application.state.start_payment_use_case = StartPaymentUseCase(
        application.state.quote_cart_use_case,
        HttpPaymentGateway(payment_client, settings.payment_service_token),
        events,
    )
    register_error_handlers(application, events)
    register_pay_error_handlers(application)
    application.include_router(pay_router)
    application.include_router(health_router)
    application.include_router(catalog_router)
    application.include_router(cart_router)
    application.include_router(order_tracking_router)
    application.include_router(order_router)
    return application


app = create_app()
