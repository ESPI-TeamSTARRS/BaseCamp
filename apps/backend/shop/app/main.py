import sys
import time

import httpx
from fastapi import FastAPI
from sqlalchemy import create_engine

from app.account_orders.application.get_my_order import GetMyOrderUseCase
from app.account_orders.application.link_guest_orders import LinkGuestOrdersUseCase
from app.account_orders.application.list_my_orders import ListMyOrdersUseCase
from app.account_orders.infrastructure.clients.http_account_profile_directory import (
    HttpAccountProfileDirectory,
)
from app.account_orders.infrastructure.repositories.sqlalchemy_account_order_reader import (
    SqlAlchemyAccountOrderReader,
)
from app.account_orders.infrastructure.repositories.sqlalchemy_guest_order_linker import (
    SqlAlchemyGuestOrderLinker,
)
from app.account_orders.presentation.router import router as account_orders_router
from app.cart.application.quote_cart import QuoteCartUseCase
from app.cart.infrastructure.repositories.sqlalchemy_cart_product_reader import (
    SqlAlchemyCartProductReader,
)
from app.cart.presentation.router import router as cart_router
from app.catalog.application.archive_product import ArchiveProductUseCase
from app.catalog.application.create_product import CreateProductUseCase
from app.catalog.application.get_admin_product import GetAdminProductUseCase
from app.catalog.application.get_product import GetProductUseCase
from app.catalog.application.list_admin_products import ListAdminProductsUseCase
from app.catalog.application.list_products import ListProductsUseCase
from app.catalog.application.update_product import UpdateProductUseCase
from app.catalog.application.upload_product_image import UploadProductImageUseCase
from app.catalog.infrastructure.repositories.sqlalchemy_admin_product_repository import (
    SqlAlchemyAdminProductRepository,
)
from app.catalog.infrastructure.repositories.sqlalchemy_product_repository import (
    SqlAlchemyProductRepository,
)
from app.catalog.infrastructure.storage.s3_product_image_storage import S3ProductImageStorage
from app.catalog.presentation.admin_router import router as catalog_admin_router
from app.catalog.presentation.router import router as catalog_router
from app.core.config import Settings
from app.core.errors import register_error_handlers
from app.core.logging.correlation_id_middleware import CorrelationIdMiddleware
from app.core.logging.email_pseudonymizer import build_pseudonymizer
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.customer_identity.application.authenticate_customer import AuthenticateCustomerUseCase
from app.customer_identity.application.authorize_operator import AuthorizeOperatorUseCase
from app.customer_identity.infrastructure.clients.http_jwks_source import HttpJwksSource
from app.customer_identity.infrastructure.clients.jwks_client_token_verifier import (
    JwksClientTokenVerifier,
)
from app.customer_identity.infrastructure.clients.jwks_key_cache import JwksKeyCache
from app.customer_identity.infrastructure.clients.system_clock import SystemClock
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
from app.pay.domain.interfaces.payment_gateway import PaymentGateway
from app.pay.error_handlers import register_pay_error_handlers
from app.pay.infrastructure.clients.http_payment_gateway import HttpPaymentGateway
from app.pay.infrastructure.clients.http_service_token_provider import (
    HttpServiceTokenProvider,
)
from app.pay.presentation.router import router as pay_router
from app.payment_confirmation.application.receive_payment_webhook import (
    ReceivePaymentWebhookUseCase,
)
from app.payment_confirmation.application.send_order_confirmation import (
    SendOrderConfirmationUseCase,
)
from app.payment_confirmation.domain.services.webhook_signature_verifier import (
    WebhookSignatureVerifier,
)
from app.payment_confirmation.error_handlers import register_payment_confirmation_error_handlers
from app.payment_confirmation.infrastructure.repositories.sqlalchemy_confirmation_unit_of_work import (
    SqlAlchemyConfirmationUnitOfWork,
)
from app.payment_confirmation.infrastructure.senders.confirmation_sender_factory import (
    ConfirmationSenderFactory,
)
from app.payment_confirmation.presentation.router import router as payment_confirmation_router
from app.payment_request.application.confirm_order_payment import ConfirmOrderPaymentUseCase
from app.payment_request.application.request_order_payment import RequestOrderPaymentUseCase
from app.payment_request.infrastructure.gateways.simulated_payment_gateway import (
    SimulatedPaymentGateway,
)
from app.payment_request.infrastructure.repositories.sqlalchemy_payment_unit_of_work import (
    SqlAlchemyPaymentUnitOfWork,
)
from app.payment_request.presentation.router import router as payment_request_router

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
    auth_timeout = httpx.Timeout(
        connect=settings.auth_connect_timeout_seconds,
        read=settings.auth_read_timeout_seconds,
        write=settings.auth_read_timeout_seconds,
        pool=settings.auth_connect_timeout_seconds,
    )
    auth_client = httpx.Client(timeout=auth_timeout, limits=httpx.Limits(max_connections=10))
    token_verifier = JwksClientTokenVerifier(
        JwksKeyCache(
            HttpJwksSource(auth_client, settings.auth_jwks_url),
            time.monotonic,
            settings.auth_jwks_ttl_seconds,
            settings.auth_jwks_min_refetch_seconds,
        ),
        settings.auth_issuer,
        settings.auth_audience,
    )
    application.state.authenticate_customer_use_case = AuthenticateCustomerUseCase(
        token_verifier, SystemClock(), events
    )
    application.state.authorize_operator_use_case = AuthorizeOperatorUseCase(
        token_verifier, SystemClock(), events, settings.admin_required_amr
    )
    admin_products = SqlAlchemyAdminProductRepository(engine)
    admin_pseudonymizer = build_pseudonymizer(settings.log_pseudonym_key)
    application.state.list_admin_products_use_case = ListAdminProductsUseCase(admin_products)
    application.state.get_admin_product_use_case = GetAdminProductUseCase(admin_products)
    application.state.create_product_use_case = CreateProductUseCase(
        admin_products, events, admin_pseudonymizer
    )
    application.state.update_product_use_case = UpdateProductUseCase(
        admin_products, events, admin_pseudonymizer
    )
    application.state.archive_product_use_case = ArchiveProductUseCase(
        admin_products, events, admin_pseudonymizer
    )
    application.state.upload_product_image_use_case = UploadProductImageUseCase(
        admin_products,
        S3ProductImageStorage(
            httpx.Client(timeout=httpx.Timeout(connect=2.0, read=10.0, write=10.0, pool=2.0)),
            endpoint=settings.s3_endpoint,
            bucket=settings.s3_bucket,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            region=settings.s3_region,
        ),
        events,
        admin_pseudonymizer,
    )
    account_reader = SqlAlchemyAccountOrderReader(engine)
    link_guest_orders = LinkGuestOrdersUseCase(
        HttpAccountProfileDirectory(auth_client, settings.auth_profile_url),
        SqlAlchemyGuestOrderLinker(engine),
        events,
        build_pseudonymizer(settings.log_pseudonym_key),
    )
    application.state.link_guest_orders_use_case = link_guest_orders
    application.state.list_my_orders_use_case = ListMyOrdersUseCase(
        account_reader, link_guest_orders, events
    )
    application.state.get_my_order_use_case = GetMyOrderUseCase(account_reader, events)
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
    gateway: PaymentGateway = (
        SimulatedPaymentGateway(engine)
        if settings.payment_provider == "simulated"
        else HttpPaymentGateway(
            payment_client,
            HttpServiceTokenProvider(
                auth_client,
                settings.auth_issue_url,
                settings.auth_client_id,
                settings.auth_client_secret,
                settings.payment_audience,
                settings.payment_scope,
                settings.payment_renew_margin_seconds,
            ),
        )
    )
    application.state.start_payment_use_case = StartPaymentUseCase(
        application.state.quote_cart_use_case, gateway, events
    )
    application.state.request_order_payment_use_case = RequestOrderPaymentUseCase(
        lambda: SqlAlchemyPaymentUnitOfWork(engine), gateway, events
    )
    application.state.confirm_order_payment_use_case = ConfirmOrderPaymentUseCase(
        lambda: SqlAlchemyPaymentUnitOfWork(engine), gateway, events
    )
    application.state.receive_payment_webhook_use_case = ReceivePaymentWebhookUseCase(
        lambda: SqlAlchemyConfirmationUnitOfWork(engine),
        WebhookSignatureVerifier(
            (settings.payment_webhook_secret, settings.payment_webhook_secret_previous),
            settings.payment_webhook_tolerance_seconds,
            time.time,
        ),
        events,
    )
    application.state.send_order_confirmation_use_case = SendOrderConfirmationUseCase(
        ConfirmationSenderFactory.build(settings),
        events,
        build_pseudonymizer(settings.log_pseudonym_key),
    )
    register_error_handlers(application, events)
    register_payment_confirmation_error_handlers(application)
    register_pay_error_handlers(application)
    application.include_router(pay_router)
    application.include_router(health_router)
    application.include_router(catalog_router)
    application.include_router(catalog_admin_router)
    application.include_router(cart_router)
    application.include_router(order_tracking_router)
    application.include_router(account_orders_router)
    application.include_router(order_router)
    application.include_router(payment_request_router)
    application.include_router(payment_confirmation_router)
    return application


app = create_app()
