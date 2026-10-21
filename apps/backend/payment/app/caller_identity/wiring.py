import time
from datetime import UTC, datetime

import httpx

from app.caller_identity.application.authenticate_caller import AuthenticateCallerUseCase
from app.caller_identity.domain.interfaces.jwks_source import JwksSource
from app.caller_identity.infrastructure.clients.http_jwks_source import HttpJwksSource
from app.caller_identity.infrastructure.clients.jwks_key_cache import JwksKeyCache
from app.caller_identity.infrastructure.clients.jwks_token_verifier import JwksTokenVerifier
from app.core.config import Settings
from app.core.events.business_event_logger import BusinessEventLogger


def build_authenticate_caller(
    settings: Settings, events: BusinessEventLogger, jwks_source: JwksSource | None = None
) -> AuthenticateCallerUseCase:
    """Assemble la verification des jetons d'`auth` (cles en cache, relues sur `kid` inconnu).

    `jwks_source` ne sert qu'aux tests (cles fournies sans reseau); en service, les cles sont lues
    sur le reseau interne avec des delais courts : `auth` arrete ne bloque jamais `payment`.
    """
    source = jwks_source or HttpJwksSource(
        httpx.Client(
            timeout=httpx.Timeout(
                connect=settings.auth_connect_timeout_seconds,
                read=settings.auth_read_timeout_seconds,
                write=settings.auth_read_timeout_seconds,
                pool=settings.auth_connect_timeout_seconds,
            ),
            limits=httpx.Limits(max_connections=5),
        ),
        settings.auth_jwks_url,
    )
    keys = JwksKeyCache(
        source,
        time.monotonic,
        settings.auth_jwks_ttl_seconds,
        settings.auth_jwks_min_refetch_seconds,
    )
    verifier = JwksTokenVerifier(
        keys,
        settings.auth_issuer,
        settings.auth_service_audience,
        settings.auth_client_audience,
    )
    return AuthenticateCallerUseCase(verifier, lambda: datetime.now(UTC), events)
