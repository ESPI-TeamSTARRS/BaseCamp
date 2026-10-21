from sqlalchemy import Engine

from app.core.config import Settings
from app.core.events.business_event_logger import BusinessEventLogger
from app.service_token.application.get_jwks import GetJwksUseCase
from app.service_token.application.issue_service_token import IssueServiceTokenUseCase
from app.service_token.application.service_token_services import ServiceTokenServices
from app.service_token.infrastructure.clients.ed25519_key_store import Ed25519KeyStore
from app.service_token.infrastructure.clients.jwt_token_signer import JwtTokenSigner
from app.service_token.infrastructure.clients.system_clock import SystemClock
from app.service_token.infrastructure.hashers.argon2_secret_hasher import Argon2SecretHasher
from app.service_token.infrastructure.repositories.sqlalchemy_rate_limiter import (
    SqlAlchemyRateLimiter,
)
from app.service_token.infrastructure.repositories.sqlalchemy_service_client_repository import (
    SqlAlchemyServiceClientRepository,
)


def build_service_token_services(
    engine: Engine, settings: Settings, events: BusinessEventLogger
) -> ServiceTokenServices:
    """Assemble les cas d'usage de la tranche avec leurs adaptateurs d'infrastructure.

    Les cles sont lues au premier usage : le service demarre (et repond sur /health) meme si les
    secrets sont absents, seule l'emission d'un jeton echoue alors (500 assaini).
    """
    key_store = Ed25519KeyStore(settings.jwt_private_key_file, settings.jwt_public_key_file)
    return ServiceTokenServices(
        issue=IssueServiceTokenUseCase(
            SqlAlchemyServiceClientRepository(engine),
            Argon2SecretHasher(),
            SqlAlchemyRateLimiter(engine, settings.service_token_rate_limit_per_minute),
            JwtTokenSigner(key_store),
            SystemClock(),
            settings.jwt_issuer,
            events,
        ),
        jwks=GetJwksUseCase(key_store),
    )
